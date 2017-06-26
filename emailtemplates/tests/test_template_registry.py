# coding=utf-8
from django.conf import settings
from django.test import TestCase
from django.core import mail
from mock import Mock

from emailtemplates.email import EmailFromTemplate
from ..registry import EmailTemplateRegistry


class EmailTemplateRegistryTest(TestCase):

    def test_register_template(self):
        registry = EmailTemplateRegistry()
        registry.register('hello_template.html')

    def test_get_help_text(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register('hello_template.html', help_text=u'Hello template',
                                   help_context={'username': u'Name of user in hello expression'})
        help_text = template_registry.get_help_text('hello_template.html')
        self.assertEqual(help_text, u'Hello template')

    def test_get_help_context(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register('hello_template.html', help_text=u'Hello template',
                                   help_context={'username': u'Name of user in hello expression'})
        help_context = template_registry.get_help_context('hello_template.html')
        self.assertIn('username', help_context)

    def test_get_email_templates(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register('hello_template.html', help_text=u'Hello template',
                                   help_context={'username': u'Name of user in hello expression'})
        template_registry.register('simple_template.html', help_text=u'Simple template')
        self.assertEqual(2, len(template_registry.get_email_template_choices()))

    def test_get_email_template_choices(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register('hello_template.html', help_text=u'Hello template',
                                   help_context={'username': u'Name of user in hello expression'})
        self.assertEqual(1, len(template_registry.get_email_template_choices()))
        template, _ = template_registry.get_email_template_choices()[0]
        self.assertEqual('hello_template.html', template)

    def test_create_eft(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register('simple_template.html', help_text=u'Simple template')
        eft = template_registry.create_eft('simple_template.html', subject=u"Ihre bestellung")
        self.assertEqual(EmailFromTemplate, type(eft))
        self.assertEqual(u"Ihre bestellung", eft.subject)




