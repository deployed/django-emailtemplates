# coding=utf-8
from __future__ import unicode_literals

import mock
from django.conf import settings
from django.test import TestCase

from ..email import EmailFromTemplate
from ..forms import EmailLayoutAdminForm, EmailTemplateAdminForm
from ..models import EmailLayout, EmailTemplate
from ..registry import AlreadyRegistered, email_templates

TITLE = "template-with-layout.html"
# LANGUAGE_CODE ("en-us") is not one of the LANGUAGES choices of the language field
LANGUAGE = "en"


def register_title():
    try:
        email_templates.register(TITLE)
    except AlreadyRegistered:
        pass


class EmailLayoutTest(TestCase):
    def setUp(self):
        self.layout = EmailLayout.objects.create(
            name="Standard",
            header_content="<div>HEADER</div>",
            footer_content="<div>FOOTER</div>",
        )

    def test_str(self):
        self.assertEqual(str(self.layout), "Standard")

    def test_wrap_content(self):
        self.assertEqual(
            self.layout.wrap_content("<p>Hello</p>"),
            "<div>HEADER</div><p>Hello</p><div>FOOTER</div>",
        )

    def test_wrap_empty_content(self):
        self.assertEqual(
            self.layout.wrap_content(""), "<div>HEADER</div><div>FOOTER</div>"
        )

    def test_no_style_tag_when_no_styles(self):
        self.assertNotIn("<style", self.layout.wrap_content("<p>Hello</p>"))

    def test_styles_are_wrapped_in_a_style_tag_before_the_header(self):
        self.layout.styles = "body { color: red; }"
        self.assertEqual(
            self.layout.wrap_content("<p>Hello</p>"),
            '<style type="text/css">body { color: red; }</style>'
            "<div>HEADER</div><p>Hello</p><div>FOOTER</div>",
        )

    def test_blank_styles_produce_no_style_tag(self):
        self.layout.styles = "   \n  "
        self.assertNotIn("<style", self.layout.wrap_content("<p>Hello</p>"))


class EmailTemplateContentTest(TestCase):
    def setUp(self):
        self.layout = EmailLayout.objects.create(
            name="Standard",
            header_content="<div>HEADER</div>",
            footer_content="<div>FOOTER</div>",
        )
        self.content = "<p>Hello</p>"

    def test_content_without_layout(self):
        email_template = EmailTemplate.objects.create(
            title=TITLE, content=self.content, subject="Subject"
        )
        self.assertEqual(email_template.get_content(), self.content)

    def test_content_with_layout(self):
        email_template = EmailTemplate.objects.create(
            title=TITLE, content=self.content, subject="Subject", layout=self.layout
        )
        self.assertEqual(
            email_template.get_content(),
            "<div>HEADER</div><p>Hello</p><div>FOOTER</div>",
        )

    @mock.patch("emailtemplates.models.logger")
    def test_layout_ignored_when_content_extends_other_template(self, mock_logger):
        content = (
            "{% extends 'emailtemplates/base.html' %}{% block main %}Hi{% endblock %}"
        )
        email_template = EmailTemplate.objects.create(
            title=TITLE, content=content, subject="Subject", layout=self.layout
        )
        self.assertEqual(email_template.get_content(), content)
        self.assertTrue(mock_logger.warning.called)


class EmailFromTemplateWithLayoutTest(TestCase):
    def setUp(self):
        self.layout = EmailLayout.objects.create(
            name="Standard",
            header_content="<div>HEADER {{ shop }}</div>",
            footer_content="<div>FOOTER</div>",
        )
        self.email_template = EmailTemplate.objects.create(
            title=TITLE,
            content="<p>Hello {{ name }}</p>",
            subject="Subject",
            language=settings.LANGUAGE_CODE,
            layout=self.layout,
        )

    def get_rendered_message(self):
        eft = EmailFromTemplate(name=TITLE, registry_validation=False)
        eft.get_object()
        eft.context.update({"name": "Antje", "shop": "Karten-Paradies"})
        eft.render_message()
        return eft.message

    def test_message_contains_layout_and_content(self):
        message = self.get_rendered_message()
        self.assertEqual(
            message,
            "<div>HEADER Karten-Paradies</div><p>Hello Antje</p><div>FOOTER</div>",
        )

    def test_message_without_layout_is_unchanged(self):
        self.email_template.layout = None
        self.email_template.save()
        self.assertEqual(self.get_rendered_message(), "<p>Hello Antje</p>")


class EmailLayoutAdminFormTest(TestCase):
    """
    Header and footer are edited as one field, so the form has to load them into it and
    split them back out on save.
    """

    def get_form_data(self, **kwargs):
        data = {
            "name": "Standard",
            "frame_0": "<div>HEADER",
            "frame_1": "</div>",
            "styles": "body { color: red; }",
        }
        data.update(kwargs)
        return data

    def test_saves_the_two_halves_into_header_and_footer(self):
        form = EmailLayoutAdminForm(data=self.get_form_data())
        self.assertTrue(form.is_valid(), form.errors)

        layout = form.save()

        layout.refresh_from_db()
        self.assertEqual(layout.header_content, "<div>HEADER")
        self.assertEqual(layout.footer_content, "</div>")
        self.assertEqual(layout.styles, "body { color: red; }")

    def test_loads_header_and_footer_of_an_existing_layout(self):
        layout = EmailLayout.objects.create(
            name="Standard", header_content="<div>H", footer_content="</div>"
        )

        form = EmailLayoutAdminForm(instance=layout)

        self.assertEqual(form.initial["frame"], ["<div>H", "</div>"])

    def test_empty_frame_is_allowed(self):
        form = EmailLayoutAdminForm(data=self.get_form_data(frame_0="", frame_1=""))
        self.assertTrue(form.is_valid(), form.errors)

        layout = form.save()

        self.assertEqual(layout.header_content, "")
        self.assertEqual(layout.footer_content, "")


class EmailTemplateAdminFormTest(TestCase):
    def setUp(self):
        register_title()
        self.layout = EmailLayout.objects.create(name="Standard")

    def get_form_data(self, **kwargs):
        data = {
            "title": TITLE,
            "layout": self.layout.pk,
            "subject": "Subject",
            "content": "<p>Hello</p>",
            "language": LANGUAGE,
            "ordering": 1,
            "created": "2026-01-01 10:00:00",
            "modified": "2026-01-01 10:00:00",
        }
        data.update(kwargs)
        return data

    def test_layout_can_be_selected(self):
        form = EmailTemplateAdminForm(data=self.get_form_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["layout"], self.layout)

    def test_layout_is_optional(self):
        form = EmailTemplateAdminForm(data=self.get_form_data(layout=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["layout"])

    def test_layout_rejected_when_content_extends_other_template(self):
        form = EmailTemplateAdminForm(
            data=self.get_form_data(
                content="{% extends 'emailtemplates/base.html' %}Hi"
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("layout", form.errors)

    def test_extends_allowed_without_layout(self):
        form = EmailTemplateAdminForm(
            data=self.get_form_data(
                layout="", content="{% extends 'emailtemplates/base.html' %}"
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
