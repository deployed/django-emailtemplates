# coding=utf-8
import mock
from django.test import TestCase

from ..email import EmailFromTemplate
from ..models import EmailLayout, EmailTemplate
from ..registry import EmailTemplateRegistry

TITLE = "preheader.html"
LANGUAGE = "pl"


class PreheaderTest(TestCase):
    def setUp(self):
        self.registry = EmailTemplateRegistry()
        self.registry.register(
            TITLE, subject="Hi {{ name }}", preheader="News for {{ name }}"
        )
        for target in ("emailtemplates.email", "emailtemplates.models"):
            patcher = mock.patch(target + ".email_templates", self.registry)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.layout = EmailLayout.objects.create(
            name="Standard",
            header_content="<title>{{ subject }}</title><span>{{ preheader }}</span>",
        )

    def render(self):
        eft = EmailFromTemplate(name=TITLE, language=LANGUAGE)
        eft.context["name"] = "Anna"
        return eft, eft.render()

    def test_new_template_gets_the_preheader_of_the_registration(self):
        email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, content="<p>x</p>"
        )
        self.assertEqual(email_template.preheader, "News for {{ name }}")

    def test_an_emptied_preheader_stays_empty(self):
        email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, content="<p>x</p>"
        )
        email_template.preheader = ""
        email_template.save()
        email_template.refresh_from_db()
        self.assertEqual(email_template.preheader, "")

    def test_layout_gets_subject_and_preheader(self):
        EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            content="<p>Body</p>",
            preheader="Only for {{ name }} & co",
            layout=self.layout,
        )
        eft, rendered = self.render()
        self.assertEqual(eft.preheader, "Only for Anna & co")
        self.assertIn("<title>Hi Anna</title>", rendered.html)
        self.assertIn("<span>Only for Anna &amp; co</span>", rendered.html)

    def test_file_template_gets_the_preheader_of_the_registration(self):
        with mock.patch(
            "emailtemplates.email.get_template",
            return_value=mock.Mock(
                render=lambda context: "{}".format(context["preheader"])
            ),
        ):
            eft, rendered = self.render()
        self.assertEqual(eft.preheader, "News for Anna")
        self.assertEqual(rendered.html, "News for Anna")

    def test_context_variables_are_not_overridden(self):
        EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE, content="{{ subject }}", subject="S"
        )
        eft = EmailFromTemplate(name=TITLE, language=LANGUAGE)
        eft.context["subject"] = "mine"
        self.assertEqual(eft.render().html, "mine")

    def test_subject_and_preheader_are_escaped_in_html(self):
        EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="{{ name }}",
            preheader="{{ name }}",
            content="<p>Body</p>",
            layout=self.layout,
        )
        eft = EmailFromTemplate(name=TITLE, language=LANGUAGE)
        eft.context["name"] = "<b>Anna</b>"
        rendered = eft.render()
        self.assertEqual(rendered.subject, "<b>Anna</b>")
        self.assertIn("<title>&lt;b&gt;Anna&lt;/b&gt;</title>", rendered.html)
        self.assertIn("<span>&lt;b&gt;Anna&lt;/b&gt;</span>", rendered.html)
