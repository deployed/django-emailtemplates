# coding=utf-8
import mock
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ..email import EmailFromTemplate
from ..forms import EmailTemplateAdminForm
from ..models import EmailTemplate
from ..registry import Block, EmailTemplateRegistry, RegistrationItem, email_templates

TITLE = "blocks_test.html"
LANGUAGE = "pl"
BLOCK = '<div class="emailtemplates-block" data-label="Order details">{{ order }}</div>'


def register_title():
    if not email_templates.is_registered(TITLE):
        email_templates.register(
            TITLE,
            help_context={"number": ("Order number", "123")},
            blocks={
                "order": ("Order details", "blocks/order.html"),
                "paid_order": (
                    "Paid order details",
                    "blocks/order.html",
                    {"paid": True},
                ),
            },
        )


class BlockTest(TestCase):
    def test_renders_its_template_with_the_context(self):
        block = Block("order", "Order details", "blocks/order.html")
        self.assertEqual(
            block.render({"number": 7}), "<table><tr><td>Order 7</td></tr></table>"
        )

    def test_extra_context_is_added(self):
        block = Block("order", "Order", "blocks/order.html", {"paid": True})
        self.assertEqual(
            block.render({"number": 7}),
            "<table><tr><td>Order 7, paid</td></tr></table>",
        )

    def test_as_html_is_a_labeled_div_with_the_variable(self):
        block = Block("order", 'Order "details" & more', "blocks/order.html")
        self.assertEqual(
            block.as_html(),
            '<div class="emailtemplates-block" data-label="Order &quot;details&quot; '
            '&amp; more">{{ order }}</div>',
        )


class RegistryBlocksTest(TestCase):
    def setUp(self):
        self.registry = EmailTemplateRegistry()
        self.registry.register(
            "a.html", blocks={"order": ("Order details", "blocks/order.html")}
        )

    def test_blocks_are_registered(self):
        blocks = self.registry.get_blocks("a.html")
        self.assertEqual([block.name for block in blocks], ["order"])
        self.assertEqual(blocks[0].label, "Order details")

    def test_blocks_context_renders_only_when_called(self):
        with mock.patch.object(Block, "render") as render:
            context = self.registry.get_blocks_context("a.html", {"number": 1})
            render.assert_not_called()
            context["order"]()
            render.assert_called_once_with({"number": 1})

    def test_variables_of_the_context_are_not_overridden(self):
        self.assertEqual(
            self.registry.get_blocks_context("a.html", {"order": "mine"}), {}
        )

    def test_unregistered_template_has_no_blocks(self):
        self.assertEqual(self.registry.get_blocks_context("other.html", {}), {})

    def test_blocks_are_listed_in_the_help_text(self):
        item = RegistrationItem(
            "a.html", blocks={"order": ("Order details", "blocks/order.html")}
        )
        self.assertIn("<b>{{ order }}</b> - Order details", item.as_form_help_text())


class EmailWithBlocksTest(TestCase):
    def setUp(self):
        register_title()

    def render(self, content, **context):
        EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="Order {{ number }}",
            content=content,
        )
        eft = EmailFromTemplate(name=TITLE, language=LANGUAGE)
        eft.context.update(context)
        return eft.render()

    def test_block_is_rendered_in_the_email(self):
        rendered = self.render("<p>Hi</p>" + BLOCK, number=7)
        self.assertEqual(
            rendered.html,
            '<p>Hi</p><div class="emailtemplates-block" data-label="Order details">'
            "<table><tr><td>Order 7</td></tr></table></div>",
        )
        self.assertEqual(rendered.text.split(), ["Hi", "Order", "7"])

    def test_block_with_extra_context(self):
        rendered = self.render("{{ paid_order }}", number=7)
        self.assertEqual(
            rendered.html, "<table><tr><td>Order 7, paid</td></tr></table>"
        )

    def test_unused_blocks_are_not_rendered(self):
        with mock.patch.object(Block, "render") as render:
            self.render("<p>No blocks</p>", number=7)
        render.assert_not_called()


@override_settings(ROOT_URLCONF="emailtemplates.tests.urls")
class BlocksPreviewTest(TestCase):
    def test_preview_renders_blocks_with_example_context(self):
        register_title()
        user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(user)
        email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, subject="S", content=BLOCK
        )
        response = self.client.get(
            reverse("email_preview", kwargs={"pk": email_template.pk})
        )
        self.assertContains(response, "<td>Order 123</td>")


@override_settings(
    EMAILTEMPLATES_RICH_TEXT=True, ROOT_URLCONF="emailtemplates.tests.urls"
)
class BlocksAdminTest(TestCase):
    def setUp(self):
        register_title()
        self.user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(self.user)
        self.email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, subject="S", content="<p>Hi</p>"
        )
        self.url = reverse(
            "admin:emailtemplates_emailtemplate_blocks", args=[self.email_template.pk]
        )

    def test_editor_offers_the_blocks_of_the_template(self):
        form = EmailTemplateAdminForm(instance=self.email_template)
        blocks = form.get_rich_text_config()["emailtemplates_blocks"]
        self.assertEqual(
            [block["label"] for block in blocks],
            ["Order details", "Paid order details"],
        )
        self.assertEqual(blocks[0]["html"], BLOCK)

    def test_blocks_are_rendered_with_the_example_context(self):
        response = self.client.get(self.url)
        self.assertEqual(
            response.json(),
            {
                "order": "<table><tr><td>Order 123</td></tr></table>",
                "paid_order": "<table><tr><td>Order 123, paid</td></tr></table>",
            },
        )

    def test_a_broken_block_is_shown_as_an_error(self):
        with mock.patch.object(Block, "render", side_effect=ValueError("broken")):
            response = self.client.get(self.url)
        self.assertIn("broken", response.json()["order"])

    def test_staff_without_view_permission_is_denied(self):
        staff = User.objects.create_user(
            "staff", "staff@example.com", "x", is_staff=True
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)


@override_settings(ROOT_URLCONF="emailtemplates.tests.urls")
class PreviewContextTest(TestCase):
    def setUp(self):
        user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(user)

    def preview(self, path, **register_kwargs):
        if not email_templates.is_registered(path):
            email_templates.register(
                path,
                help_context={"number": ("Number", "1"), "name": "Name"},
                **register_kwargs
            )
        email_template = EmailTemplate.objects.create(
            title=path,
            language=LANGUAGE,
            subject="S",
            content="{{ number }} {{ name }}",
        )
        return self.client.get(
            reverse("email_preview", kwargs={"pk": email_template.pk})
        ).content.decode()

    def test_preview_context_updates_the_help_context_examples(self):
        self.assertEqual(
            self.preview("preview_dict.html", preview_context={"number": 7}),
            "7 &lt;name&gt;",
        )

    def test_preview_context_may_be_a_callable(self):
        calls = []

        def preview_context():
            calls.append(1)
            return {"name": "Anna"}

        self.assertEqual(
            self.preview("preview_callable.html", preview_context=preview_context),
            "1 Anna",
        )
        self.assertEqual(calls, [1])
