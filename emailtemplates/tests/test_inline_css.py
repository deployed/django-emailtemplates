# coding=utf-8
import mock
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ..checks import check_css_inliner
from ..email import EmailFromTemplate
from ..models import EmailLayout, EmailTemplate

LANGUAGE = "pl"


class InlineCssTest(TestCase):
    def setUp(self):
        layout = EmailLayout.objects.create(
            name="Standard",
            styles="h2 { color: #6b6bc5; } p { margin: 0; }",
            header_content="<div>",
            footer_content="</div>",
        )
        self.email_template = EmailTemplate.objects.create(
            title="inline.html",
            language=LANGUAGE,
            subject="S",
            content='<h2>Hello</h2><p style="color: red">{{ name }}</p>',
            layout=layout,
        )

    def render(self):
        eft = EmailFromTemplate(
            name="inline.html", language=LANGUAGE, registry_validation=False
        )
        eft.context["name"] = "Anna"
        return eft.render()

    @override_settings(EMAILTEMPLATES_INLINE_CSS=True)
    def test_styles_of_the_layout_are_inlined(self):
        rendered = self.render()
        self.assertIn('<h2 style="color: #6b6bc5;">Hello</h2>', rendered.html)
        self.assertIn('<p style="margin: 0;color: red">Anna</p>', rendered.html)
        self.assertNotIn("<style", rendered.html)
        self.assertEqual(rendered.text, "Hello\n\nAnna")

    def test_styles_are_not_inlined_by_default(self):
        rendered = self.render()
        self.assertIn("<style", rendered.html)
        self.assertIn("<h2>Hello</h2>", rendered.html)

    @override_settings(
        EMAILTEMPLATES_INLINE_CSS=True, ROOT_URLCONF="emailtemplates.tests.urls"
    )
    def test_preview_shows_the_inlined_email(self):
        user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(user)
        with mock.patch(
            "emailtemplates.views.email_templates.get_preview_context", return_value={}
        ):
            response = self.client.get(
                reverse("email_preview", kwargs={"pk": self.email_template.pk})
            )
        self.assertContains(response, '<h2 style="color: #6b6bc5;">Hello</h2>')

    @override_settings(EMAILTEMPLATES_INLINE_CSS=True)
    def test_check_requires_css_inline(self):
        self.assertEqual(check_css_inliner(None), [])
        with mock.patch.dict("sys.modules", {"css_inline": None}):
            errors = check_css_inliner(None)
        self.assertEqual([error.id for error in errors], ["emailtemplates.E001"])
