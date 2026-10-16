# coding=utf-8
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..forms import EmailTemplateAdminForm
from ..models import EmailLayout, EmailTemplate
from ..registry import email_templates
from ..widgets import EmailContentEditor

TITLE = "live_preview.html"
LANGUAGE = "pl"


class LivePreviewTest(TestCase):
    def setUp(self):
        if not email_templates.is_registered(TITLE):
            email_templates.register(TITLE, help_context={"name": ("Name", "Anna")})
        self.layout = EmailLayout.objects.create(
            name="Standard",
            header_content="<title>{{ subject }}</title><div>",
            footer_content="</div>",
        )
        self.email_template = EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="Saved",
            content="<p>Saved content</p>",
        )
        self.url = reverse(
            "admin:emailtemplates_emailtemplate_preview", args=[self.email_template.pk]
        )
        self.client.force_login(
            User.objects.create_superuser("admin", "a@example.com", "x")
        )

    def preview(self, **data):
        data.setdefault("content", "<p>Hello {{ name }}</p>")
        return self.client.post(self.url, data).json()

    def test_renders_the_unsaved_form_with_the_example_context(self):
        result = self.preview(subject="Hi {{ name }}", layout=self.layout.pk)
        self.assertEqual(
            result["html"], "<title>Hi Anna</title><div><p>Hello Anna</p></div>"
        )

    def test_nothing_is_saved(self):
        self.preview(subject="Changed", layout=self.layout.pk)
        self.email_template.refresh_from_db()
        self.assertEqual(self.email_template.content, "<p>Saved content</p>")
        self.assertEqual(self.email_template.subject, "Saved")
        self.assertIsNone(self.email_template.layout)

    def test_template_tags_encoded_by_the_rich_text_editor_are_fixed(self):
        result = self.preview(content="<p>{% if 2 &gt; 1 %}Yes{% endif %}</p>")
        self.assertEqual(result["html"], "<p>Yes</p>")

    def test_without_a_layout(self):
        self.assertEqual(self.preview(layout="")["html"], "<p>Hello Anna</p>")

    def test_content_that_cannot_be_rendered_returns_the_error(self):
        result = self.preview(content="<p>{% if %}</p>")
        self.assertNotIn("html", result)
        self.assertTrue(result["error"])

    def test_staff_without_view_permission_is_denied(self):
        staff = User.objects.create_user("staff", "s@example.com", "x", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(self.url, {"content": "x"}).status_code, 403)

    def test_the_editor_gets_the_url_and_the_preview_pane(self):
        form = EmailTemplateAdminForm(instance=self.email_template)
        html = str(form["content"])
        self.assertIn("emailtemplates-content-editor__preview", html)
        start = html.index('data-content-editor="') + len('data-content-editor="')
        options = json.loads(
            html[start : html.index('"', start)]
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        self.assertEqual(options["previewUrl"], self.url)
        self.assertTrue(options["previewError"])


class EditorWidthTest(TestCase):
    def width(self, config):
        return EmailContentEditor(rich_text_config=config).get_editor_width()

    def test_a_width_in_pixels_is_the_least_width_of_the_editor_column(self):
        self.assertEqual(self.width({"width": 1000}), 1000)
        self.assertEqual(self.width({"width": "900px"}), 900)

    def test_other_widths_keep_the_default(self):
        for config in ({"width": "100%"}, {"width": "auto"}, {}, None, {"width": True}):
            self.assertIsNone(self.width(config))

    def test_the_width_is_rendered_as_a_css_variable(self):
        html = EmailContentEditor(rich_text_config={"width": 1000}).render(
            "content", ""
        )
        self.assertIn('style="--emailtemplates-editor-width: 1000px"', html)
        html = EmailContentEditor(rich_text_config={"width": "100%"}).render(
            "content", ""
        )
        self.assertNotIn("--emailtemplates-editor-width", html)
