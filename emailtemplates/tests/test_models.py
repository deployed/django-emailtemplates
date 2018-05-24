# encoding: utf-8
from __future__ import unicode_literals
import mock
import os

from django.core import mail
from django.core.files import File
from django.test import TestCase

from emailtemplates.helpers import TemplateSourceLoader
from emailtemplates.models import EmailTemplate, MassEmailMessage, MassEmailAttachment


class EmailTemplateTest(TestCase):
    def setUp(self):
        self.default_content = '<h1>TEST DEFAULT CONTENT</h1>'
        self.email_template = EmailTemplate.objects.create(title='template-1.html')

    @mock.patch.object(TemplateSourceLoader, 'get_source')
    def test_get_default_content(self, mock_source):
        mock_source.return_value = self.default_content
        self.assertEqual(self.email_template.get_default_content(), self.default_content)

    @mock.patch.object(TemplateSourceLoader, 'get_source', mock.Mock(side_effect=Exception('error...')))
    def test_get_empty_default_content_if_error(self):
        self.assertEqual(self.email_template.get_default_content(), '')

    @mock.patch.object(TemplateSourceLoader, 'get_source')
    def test_save_default_content(self, mock_source):
        mock_source.return_value = self.default_content
        email_template = EmailTemplate.objects.create(title='template-2.html')
        self.assertEqual(email_template.content, self.default_content)

    @mock.patch.object(TemplateSourceLoader, 'get_source')
    def test_do_not_override_existing_content(self, mock_source):
        mock_source.return_value = self.default_content
        email_template = EmailTemplate.objects.create(title='template-2.html', content='<h1>New content</h1>')
        self.assertEqual(email_template.content, '<h1>New content</h1>')


class MassEmailMessageTest(TestCase):
    def setUp(self):
        self.mass_email_message = MassEmailMessage.objects.create(
            subject="Temat maila",
            content="<p>Treść emaila</p>"
        )
        self.attachment_filepath = os.path.join(os.path.dirname(__file__), 'data', 'example_file.txt')

    def test_send(self):
        recipients = ["person@example.com"]
        sent = self.mass_email_message.send(recipients)
        self.assertTrue(sent)
        self.assertTrue(self.mass_email_message.sent)
        self.assertEqual(mail.outbox[0].to, recipients)
        self.assertEqual(mail.outbox[0].subject, "Temat maila")
        self.assertEqual(mail.outbox[0].body, "<p>Treść emaila</p>")

    def test_send_with_attachments(self):
        attachment = MassEmailAttachment.objects.create(
            attachment_file=File(open(self.attachment_filepath, 'r'), 'example_file.txt'), 
            mass_email_message=self.mass_email_message,
        )
        recipients = ["person@example.com"]
        sent = self.mass_email_message.send(recipients)
        self.assertTrue(sent)
        self.assertEqual(
            mail.outbox[0].attachments, 
            [('example_file.txt', u'Some content of example file.', 'text/plain')],
        )