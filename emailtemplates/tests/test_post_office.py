# coding=utf-8
from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase

from ..contrib.post_office import render_for_post_office
from ..models import EmailAttachment, EmailTemplate
from ..registry import NotRegistered, email_templates

TITLE = "post_office_test.html"
LANGUAGE = "pl"


class RenderForPostOfficeTest(TestCase):
    def setUp(self):
        if not email_templates.is_registered(TITLE):
            email_templates.register(TITLE)
        self.email_template = EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="Order {{ number }}",
            content='<p>Hello {{ name }}, <a href="{{ url }}">pay</a>.</p>',
        )
        mail.outbox = []

    def render(self, **kwargs):
        return render_for_post_office(
            TITLE,
            {"number": 7, "name": "Anna", "url": "https://x.pl/pay/"},
            language=LANGUAGE,
            **kwargs,
        )

    def test_returns_kwargs_of_mail_send(self):
        self.assertEqual(
            self.render(),
            {
                "subject": "Order 7",
                "message": "Hello Anna, [pay](https://x.pl/pay/).",
                "html_message": '<p>Hello Anna, <a href="https://x.pl/pay/">pay</a>.</p>',
            },
        )

    def test_sends_nothing(self):
        self.render()
        self.assertEqual(mail.outbox, [])

    def test_file_attachments_are_included(self):
        attachment = EmailAttachment.objects.create(name="Terms", send_as_link=False)
        attachment.attachment_file.save("terms.txt", ContentFile(b"Terms"), save=True)
        self.email_template.attachments.add(attachment)
        attachments = self.render()["attachments"]
        self.assertEqual(
            list(attachments), [attachment.attachment_file.name.split("/")[-1]]
        )
        self.assertEqual(next(iter(attachments.values())).read(), b"Terms")
        attachment.attachment_file.delete()

    def test_attachments_sent_as_links_are_in_the_context(self):
        attachment = EmailAttachment.objects.create(
            name="Terms",
            attachment_file="emails/attachments/terms.pdf",
            send_as_link=True,
        )
        self.email_template.attachments.add(attachment)
        self.email_template.content = (
            "{% for name, url in default_attachments %}{{ name }}{% endfor %}"
        )
        self.email_template.save()
        message = self.render()
        self.assertNotIn("attachments", message)
        self.assertEqual(message["html_message"], "Terms")

    def test_unregistered_template_is_rejected(self):
        with self.assertRaises(NotRegistered):
            render_for_post_office("not_registered.html")
