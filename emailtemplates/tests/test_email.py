# coding=utf-8
import mock
import os

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils.html import escape
from mock import Mock

from ..email import EmailFromTemplate
from ..email import logger as email_logger
from ..helpers import substr
from ..models import EmailTemplate
from ..registry import email_templates, NotRegistered, EmailTemplateRegistry


class CheckEmail(TestCase):
    def check_email_was_sent(self, eft, to):
        self.assertTrue(len(mail.outbox) > 0)
        msg = mail.outbox[0]
        self.assertTrue(settings.DEFAULT_FROM_EMAIL in msg.from_email)
        self.assertEqual(msg.content_subtype, 'html')
        self.assertEqual(msg.subject, eft.subject)
        self.assertEqual(msg.body, eft.message)
        self.assertTrue('Message-Id' in msg.message())
        self.assertEqual(msg.to, to)


class EmailFromTemplateTest(CheckEmail):
    def setUp(self):
        mail.outbox = []
        email_templates = EmailTemplateRegistry()
        email_logger.warning = Mock()
        self.attachment_filepath = os.path.join(os.path.dirname(__file__), 'data', 'example_file.txt')

    def test_empty_object(self):
        eft = EmailFromTemplate(registry_validation=False)
        self.assertTrue(isinstance(eft, object))
        eft.render_message()
        to = ['to@example.com']
        eft.send_email(to)
        self.check_email_was_sent(eft, to)

    def test_with_empty_db_object(self):
        eft = EmailFromTemplate(registry_validation=False)
        eft.get_object()
        email_logger.warning.assert_has_calls(substr("Can't find EmailTemplate object in database"))
        email_logger.warning.assert_has_calls(substr("template in the filesystem, will use very default one"))
        eft.render_message()
        to = ['to@example.com']
        eft.send_email(to)
        self.check_email_was_sent(eft, to)

    def test_init_check_email_templates_registry(self):
        with self.assertRaises(NotRegistered):
            email_template = EmailFromTemplate("some_template.html")
        email_templates.register("some_template.html")
        email_template = EmailFromTemplate("some_template.html")
        self.assertTrue(email_templates.is_registered("some_template.html"))

    def test_send_attachment_paths(self):
        eft = EmailFromTemplate(registry_validation=False)
        to = ['to@example.com']
        eft.send(to, attachment_paths=[self.attachment_filepath])
        self.check_email_was_sent(eft, to)
        self.assertEqual(
            mail.outbox[0].attachments, 
            [('example_file.txt', u'Some content of example file.', 'text/plain')],
        )


class EmailFromTemplateWithFixturesTest(CheckEmail):
    def setUp(self):
        self.language = 'pl'
        email_templates = EmailTemplateRegistry()
        self.support_template = EmailTemplate.objects.create(
            language=self.language,
            title='support_respond.html',
            subject="Test",
            content="Support: {{ user_name }}"
        )
        mail.outbox = []
        email_logger.debug = Mock()

    def test_support_database_template(self):
        eft = EmailFromTemplate(name='support_respond.html', language=self.language, registry_validation=False)
        eft.get_object()
        email_logger.debug.assert_called_with(substr("Got template"))
        self.assertEqual(eft.template_source, 'database')
        eft.render_message()
        to = ['tester1@example.com', 'tester2@example.com']
        eft.send_email(to)
        self.check_email_was_sent(eft, to)

    def test_support_database_template_without_title(self):
        self.support_template.subject = ''
        self.support_template.save(update_fields=['subject'])
        eft = EmailFromTemplate(
            name='support_respond.html',
            subject='default email title',
            language=self.language,
            registry_validation=False
        )
        eft.get_object()
        self.assertEqual(eft.subject, 'default email title')

    def test_friends_invitation_no_database_or_filesystem_template(self):
        eft = EmailFromTemplate(registry_validation=False)
        eft.context = {'user_name': 'Alibaba',
                       'personal_message': "I'd like you te be site member!",
                       'landing_url': 'http://example.com/followers/612/'}
        eft.template = "{{ user_name }}, {{ personal_message }} {{ landing_url }}"
        eft.render_message()
        self.assertEqual(eft.message,
                         escape(u"Alibaba, I'd like you te be site member! http://example.com/followers/612/"))
        to = ['tester@example.com']
        self.assertEqual(eft.template_source, 'default')
        eft.send_email(to)
        self.check_email_was_sent(eft, to)
