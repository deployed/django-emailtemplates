# coding=utf-8
import json

import mock
from django.contrib.auth.models import User
from django.core.checks import Warning
from django.test import TestCase, override_settings

from ..checks import check_rich_text_editor
from ..forms import EmailTemplateAdminForm
from ..models import EmailLayout, EmailTemplate
from ..registry import EmailTemplateRegistry, email_templates
from ..rich_text import (
    misplaced_template_tags,
    rich_text_available,
    rich_text_config,
    rich_text_problem,
    unescape_template_tags,
)
from ..widgets import EmailContentEditor

TITLE = "rich_text_test.html"
LANGUAGE = "pl"
MISPLACED = "<ul><li>a</li>{% if x %}<li>b</li>{% endif %}</ul>"


def register_title():
    if not email_templates.is_registered(TITLE):
        email_templates.register(
            TITLE,
            help_context={
                "first_name": ("First name of the user", "Anna"),
                "activation_url": "Account activation link",
            },
        )


def editor_options(form):
    """Options content_editor.js gets from the rendered content field."""
    html = str(form["content"])
    start = html.index('data-content-editor="') + len('data-content-editor="')
    end = html.index('"', start)
    return json.loads(html[start:end].replace("&quot;", '"').replace("&amp;", "&"))


class UnescapeTemplateTagsTest(TestCase):
    def test_entities_in_template_tags_are_decoded(self):
        self.assertEqual(
            unescape_template_tags(
                "<p>{% if count &gt; 1 and name == &quot;A&amp;B&quot; %}x{% endif %}</p>"
            ),
            '<p>{% if count > 1 and name == "A&B" %}x{% endif %}</p>',
        )

    def test_non_breaking_spaces_in_template_tags_become_spaces(self):
        self.assertEqual(
            unescape_template_tags("{{\xa0first_name\xa0}} {%&nbsp;now 'Y' %}"),
            "{{ first_name }} {% now 'Y' %}",
        )

    def test_text_outside_template_tags_is_left_alone(self):
        content = "<p>Tom &amp; Jerry &gt; {{ name }}</p>"
        self.assertEqual(unescape_template_tags(content), content)


class RichTextProblemTest(TestCase):
    def test_tags_between_table_rows_are_found(self):
        content = (
            "<table><tr><td>A</td></tr>{% for i in items %}<tr><td>{{ i }}</td></tr>"
            "{% endfor %}</table>"
        )
        self.assertEqual(
            misplaced_template_tags(content), ["{% for i in items %}", "{% endfor %}"]
        )

    def test_tags_between_list_items_and_cells_are_found(self):
        self.assertEqual(
            misplaced_template_tags(MISPLACED), ["{% if x %}", "{% endif %}"]
        )
        content = "<table><tr>{% if x %}<td>b</td>{% endif %}</tr></table>"
        self.assertEqual(
            misplaced_template_tags(content), ["{% if x %}", "{% endif %}"]
        )

    def test_tags_inside_cells_items_and_paragraphs_are_fine(self):
        content = (
            "{% if paid %}<p>Paid</p>{% endif %}"
            "<table><tr><td>{% if x %}{{ x }}{% endif %}<br>{{ y }}</td></tr></table>"
            "<ul><li>{{ a }}</li></ul><p>{% now 'Y' %}</p>"
        )
        self.assertEqual(misplaced_template_tags(content), [])
        self.assertEqual(rich_text_problem(content), "")

    def test_problems_name_the_reason(self):
        self.assertIn("{% if x %}, {% endif %}", rich_text_problem(MISPLACED))
        self.assertIn("{% extends %}", rich_text_problem("{% extends 'a.html' %}"))


class RichTextConfigTest(TestCase):
    def test_project_config_for_the_website_is_not_used(self):
        with mock.patch(
            "tinymce.settings.DEFAULT_CONFIG",
            {
                "license_key": "gpl",
                "content_css": "/static/site.css",
                "setup": "siteSetup",
                "plugins": "image",
            },
        ):
            config = rich_text_config()
        self.assertEqual(config["license_key"], "gpl")
        self.assertEqual(
            config["content_css"],
            ["default", "/static/emailtemplates/rich_text_content.css"],
        )
        self.assertNotIn("setup", config)
        self.assertNotIn("image", config["plugins"])

    def test_urls_are_kept_as_typed(self):
        config = rich_text_config()
        self.assertFalse(config["convert_urls"])
        self.assertEqual(config["entity_encoding"], "raw")

    def test_every_button_is_on_the_toolbar_variables_and_blocks_first(self):
        config = rich_text_config()
        self.assertEqual(config["toolbar_mode"], "wrap")
        self.assertTrue(
            config["toolbar"].startswith(
                "emailtemplates_variables emailtemplates_blocks"
            )
        )
        self.assertIn("emailtemplates", config["plugins"])

    @override_settings(EMAILTEMPLATES_RICH_TEXT_CONFIG={"height": 300})
    def test_config_can_be_extended_in_settings(self):
        config = rich_text_config()
        self.assertEqual(config["height"], 300)
        self.assertFalse(config["convert_urls"])

    def test_variables_and_blocks_are_passed_to_the_editor(self):
        registry = EmailTemplateRegistry()
        registry.register(
            "a.html", blocks={"order": ("Order details", "blocks/order.html")}
        )
        config = rich_text_config(
            variables=[("first_name", "First name")],
            blocks=registry.get_blocks("a.html"),
            blocks_url="/blocks/",
        )
        self.assertEqual(
            config["emailtemplates_variables"],
            [{"name": "first_name", "description": "First name"}],
        )
        self.assertEqual(config["emailtemplates_blocks"][0]["name"], "order")
        self.assertIn("{{ order }}", config["emailtemplates_blocks"][0]["html"])
        self.assertEqual(config["emailtemplates_blocks_url"], "/blocks/")

    def test_styles_of_the_layout_are_shown_in_the_editor(self):
        config = rich_text_config(styles=".btn { color: red; }")
        self.assertTrue(config["content_style"].endswith(".btn { color: red; }"))

    @override_settings(EMAILTEMPLATES_RICH_TEXT_CONFIG={"content_css": "/email.css"})
    def test_styles_of_blocks_and_chips_can_be_replaced(self):
        self.assertEqual(rich_text_config()["content_css"], "/email.css")

    @override_settings(
        EMAILTEMPLATES_RICH_TEXT_CONFIG={
            "style_formats": [{"title": "Button", "selector": "a", "classes": "btn"}]
        }
    )
    def test_style_formats_add_the_formats_button(self):
        self.assertIn("| blocks styles |", rich_text_config()["toolbar"])

    def test_no_formats_button_without_style_formats(self):
        self.assertNotIn("styles", rich_text_config()["toolbar"])


class RichTextAvailableTest(TestCase):
    @override_settings(EMAILTEMPLATES_RICH_TEXT=True)
    def test_available_when_opted_in_with_tinymce(self):
        self.assertTrue(rich_text_available())
        with mock.patch("emailtemplates.rich_text.TinyMCE", None):
            self.assertFalse(rich_text_available())

    def test_off_by_default(self):
        self.assertFalse(rich_text_available())


class CheckTest(TestCase):
    @override_settings(EMAILTEMPLATES_RICH_TEXT=True)
    def test_check_warns_when_rich_text_is_on_without_tinymce(self):
        self.assertEqual(check_rich_text_editor(None), [])
        with mock.patch("emailtemplates.checks.apps.is_installed", return_value=False):
            errors = check_rich_text_editor(None)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Warning)
        self.assertEqual(errors[0].id, "emailtemplates.W001")


@override_settings(EMAILTEMPLATES_RICH_TEXT=True)
class ContentEditorFormTest(TestCase):
    def setUp(self):
        register_title()
        self.email_template = EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="Hello",
            content="<p>Hello {{ first_name }}</p>",
        )

    def get_form(self, **kwargs):
        data = {
            "title": TITLE,
            "subject": "Hello",
            "content": "<p>Hello {{ first_name }}</p>",
            "language": LANGUAGE,
            "ordering": 1,
            "created": "2026-01-01 10:00:00",
            "modified": "2026-01-01 10:00:00",
        }
        data.update(kwargs)
        return EmailTemplateAdminForm(data=data, instance=self.email_template)

    def test_content_starts_in_the_rich_text_editor(self):
        form = EmailTemplateAdminForm(instance=self.email_template)
        self.assertIsInstance(form.fields["content"].widget, EmailContentEditor)
        html = str(form["content"])
        self.assertIn('data-start="rich"', html)
        self.assertIn('data-editor="rich"', html)

    def test_editor_offers_the_variables_and_the_blocks_url_of_the_template(self):
        form = EmailTemplateAdminForm(instance=self.email_template)
        config = editor_options(form)["richText"]
        self.assertEqual(
            [variable["name"] for variable in config["emailtemplates_variables"]],
            ["activation_url", "first_name"],
        )
        self.assertEqual(
            config["emailtemplates_blocks_url"],
            "/admin/emailtemplates/emailtemplate/%s/blocks/" % self.email_template.pk,
        )

    def test_content_the_rich_text_editor_would_break_starts_as_html_code(self):
        self.email_template.content = MISPLACED
        html = str(EmailTemplateAdminForm(instance=self.email_template)["content"])
        self.assertIn('data-start="html"', html)
        self.assertIn("{% if x %}, {% endif %}", html)

    def test_the_submitted_content_decides_the_editor(self):
        # e.g. the form is shown again with errors: the content is the one submitted
        form = self.get_form(content=MISPLACED, subject="")
        html = str(form["content"])
        self.assertIn('data-start="html"', html)
        self.assertIn("{% if x %}, {% endif %}", html)

    def test_messages_for_switching_are_passed_to_the_script(self):
        problems = editor_options(EmailTemplateAdminForm(instance=self.email_template))[
            "problems"
        ]
        self.assertIn("%(tags)s", problems["misplaced"])
        self.assertIn("{% extends %}", problems["extends"])
        self.assertIn("%(tags)s", problems["changed"])

    @override_settings(EMAILTEMPLATES_RICH_TEXT=False)
    def test_html_code_only_when_rich_text_is_off(self):
        form = EmailTemplateAdminForm(instance=self.email_template)
        html = str(form["content"])
        self.assertIn('data-start="html"', html)
        self.assertNotIn('data-editor="rich"', html)
        self.assertIsNone(editor_options(form)["richText"])
        self.assertNotIn("tinymce", str(form.media))

    def test_media_starts_the_editors_with_content_editor_js(self):
        media = str(EmailTemplateAdminForm(instance=self.email_template).media)
        self.assertIn("tinymce/tinymce.min.js", media)
        self.assertIn("emailtemplates/content_editor.js", media)
        self.assertNotIn("emailtemplates/code_editor.js", media)
        self.assertNotIn("django_tinymce/init_tinymce.js", media)

    def test_template_tags_encoded_by_the_rich_text_editor_are_fixed(self):
        form = self.get_form(content="<p>{% if count &gt; 1 %}Hi{% endif %}</p>")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["content"], "<p>{% if count > 1 %}Hi{% endif %}</p>"
        )

    def test_html_outside_template_tags_is_saved_as_typed(self):
        form = self.get_form(content="<p>a &gt; b {{ a|default:'&gt;' }}</p>")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["content"], "<p>a &gt; b {{ a|default:'>' }}</p>"
        )

    def test_html_code_may_use_extends_without_a_layout(self):
        form = self.get_form(
            content="{% extends 'emails/base.html' %}{% block body %}Hi{% endblock %}",
        )
        self.assertTrue(form.is_valid(), form.errors)


@override_settings(EMAILTEMPLATES_RICH_TEXT=True)
class ContentEditorLayoutStylesTest(TestCase):
    def test_form_passes_the_styles_of_the_layout(self):
        register_title()
        layout = EmailLayout.objects.create(name="Standard", styles="p { margin: 0; }")
        email_template = EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="S",
            content="<p>Hi</p>",
            layout=layout,
        )
        config = editor_options(EmailTemplateAdminForm(instance=email_template))
        self.assertIn("p { margin: 0; }", config["richText"]["content_style"])


@override_settings(
    EMAILTEMPLATES_RICH_TEXT=True, ROOT_URLCONF="emailtemplates.tests.urls"
)
class ContentEditorAdminTest(TestCase):
    def test_change_page_loads_the_content_editor(self):
        register_title()
        user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(user)
        email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, subject="Hi", content="<p>Hi</p>"
        )
        response = self.client.get(
            "/admin/emailtemplates/emailtemplate/%s/change/" % email_template.pk
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tinymce/tinymce.min.js")
        self.assertContains(response, "emailtemplates/content_editor.js")
        self.assertContains(response, "data-content-editor=")
