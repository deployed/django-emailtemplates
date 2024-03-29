# coding=utf-8
from django.test import TestCase
from django.utils.translation import gettext as _

from ..registry import EmailTemplateRegistry, RegistrationItem, HelpContext


class HelpContextTest(TestCase):
    def test_get_help_keys(self):
        help_context = HelpContext(
            {
                "username": ("Name of user in hello expression", "superman_90"),
                "full_name": ("Full user name", "John Smith"),
                "property": "Some other property",
            }
        )
        self.assertDictEqual(
            help_context.get_help_keys(),
            {
                "username": "Name of user in hello expression",
                "full_name": "Full user name",
                "property": "Some other property",
            },
        )

    def test_get_help_values(self):
        help_context = HelpContext(
            {
                "username": ("Name of user in hello expression", "superman_90"),
                "full_name": ("Full user name", "John Smith"),
                "property": "Some other property",
            }
        )
        self.assertDictEqual(
            help_context.get_help_values(),
            {
                "username": "superman_90",
                "full_name": "John Smith",
                "property": "<property>",
            },
        )


class RegistrationItemTest(TestCase):
    def test_context_description(self):
        item = RegistrationItem(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        self.assertIn("<b>{{ username }}</b>", item.context_description())

    def test_as_form_help_text(self):
        item = RegistrationItem(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        self.assertEqual(str, type(item.as_form_help_text()))
        self.assertIn(_("USAGE"), item.as_form_help_text())
        self.assertIn(_("CONTEXT"), item.as_form_help_text())

    def test_as_form_choice(self):
        item = RegistrationItem(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        self.assertEqual(tuple, type(item.as_form_choice()))

    def test_safe_defaults(self):
        item = RegistrationItem("hello_template.html")
        self.assertEqual(str, type(item.help_text))
        self.assertEqual(dict, type(item.help_context))
        self.assertEqual(tuple, type(item.as_form_choice()))


class EmailTemplateRegistryTest(TestCase):
    def test_is_registered(self):
        registry = EmailTemplateRegistry()
        registry.register("hello_template.html")
        self.assertTrue(registry.is_registered("hello_template.html"))

    def test_get_subject(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register("hello_template.html", subject="subject")
        self.assertEqual(
            template_registry.get_subject("hello_template.html"), "subject"
        )

    def test_get_help_text(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        help_text = template_registry.get_help_text("hello_template.html")
        self.assertEqual(help_text, "Hello template")

    def test_get_help_context(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        help_context = template_registry.get_help_context("hello_template.html")
        self.assertIn("username", help_context)

    def test_get_help_content(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={
                "username": ("Name of user in hello expression", "superman_90"),
                "full_name": ("Full user name", "John Smith"),
                "property": "Some other property",
            },
        )
        help_content = template_registry.get_help_content("hello_template.html")
        self.assertDictEqual(
            help_content,
            {
                "username": "superman_90",
                "full_name": "John Smith",
                "property": "<property>",
            },
        )

    def test_get_email_templates(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        template_registry.register("simple_template.html", help_text="Simple template")
        self.assertEqual(2, len(template_registry.email_template_choices()))

    def test_email_template_choices(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        self.assertEqual(1, len(template_registry.email_template_choices()))
        template, _ = template_registry.email_template_choices()[0]
        self.assertEqual("hello_template.html", template)

    def test_registration_items(self):
        template_registry = EmailTemplateRegistry()
        template_registry.register(
            "hello_template.html",
            help_text="Hello template",
            help_context={"username": "Name of user in hello expression"},
        )
        items = list(template_registry.registration_items())
        self.assertEqual(1, len(items))
        self.assertEqual("hello_template.html", items[0].path)
