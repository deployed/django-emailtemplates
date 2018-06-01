# encoding: utf-8
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from emailtemplates.helpers import mass_mailing_recipients


def recipients_test_function():
    return ['user@example.com', 'another@example.com']

class HelpersTest(TestCase):

    def test_mass_mailing_recipients(self):
        User = get_user_model()
        User.objects.create(username="mike", email="mike@example.com", is_active=True)
        User.objects.create(username="john", email="john@example.com", is_active=False)
        User.objects.create(username="paul", is_active=True)
        self.assertEqual(list(mass_mailing_recipients()), ["mike@example.com"])
    
    @override_settings(MASS_EMAIL_RECIPIENTS='emailtemplates.tests.test_helpers.recipients_test_function')
    def test_mass_mailing_recipients_from_settings(self):
        self.assertEqual(mass_mailing_recipients(), ['user@example.com', 'another@example.com'])
