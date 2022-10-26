# coding=utf-8
import logging

from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class HelpContext(object):
    """
    Provides helpers methods for displaying help context keys (descriptions) and values (examples).
    """

    def __init__(self, help_context):
        self.help_context = help_context or {}

    def get_help_keys(self):
        """
        Returns dict of help_context keys (description texts used in `EmailRegistry.register()` method).
        """
        help_keys = {}
        for k, v in self.help_context.items():
            if isinstance(v, tuple):
                help_keys[k] = v[0]
            else:
                help_keys[k] = v
        return help_keys

    def get_help_values(self):
        """
        Returns dict of help_context values (example values submitted in `EmailRegistry.register()` method).
        """
        help_values = {}
        for k, v in self.help_context.items():
            if isinstance(v, tuple) and len(v) == 2:
                help_values[k] = v[1]
            else:
                help_values[k] = "<%s>" % k
        return help_values


class RegistrationItem(object):
    def __init__(self, path, help_text="", help_context=None, name="", subject=""):
        self.name = name or path
        self.path = path
        self.help_text = help_text
        self.subject = subject
        self.help_context_obj = HelpContext(help_context)

    @property
    def help_context(self):
        return self.help_context_obj.get_help_keys()

    def _context_key(self, key):
        return "<b>{{ %s }}</b>" % key

    def context_description(self):
        help_text_item = (
            lambda k, v: "%s - %s" % (self._context_key(k), v)
            if v
            else "%s" % self._context_key(k)
        )
        return "<br/>".join(
            [
                help_text_item(k, v)
                for (k, v) in sorted(self.help_context_obj.get_help_keys().items())
            ]
        )

    def as_form_help_text(self):
        item_help_text = (
            _("<b>USAGE: %s</b>") % self.help_text if self.help_text else ""
        )
        item_help_context = (
            _("<b>CONTEXT:</b><br/>%s") % self.context_description()
            if self.help_context_obj.get_help_keys()
            else ""
        )
        return "<br/>".join((item_help_text, item_help_context))

    def as_form_choice(self):
        return self.path, self.name

    def get_help_content(self):
        return self.help_context_obj.get_help_values()


class EmailTemplateRegistry(object):
    def __init__(self):
        self._registry = {}

    def register(self, path, name="", help_text=None, help_context=None, subject=""):
        """
        Registers email template.

        Example usage:
            email_templates.register('hello_template.html', help_text='Hello template',
                help_context={'username': 'Name of user in hello expression'})

        :param name: Template name [optional]
        :param path: Template file path. It will become immutable registry lookup key.
        :param help_text: Help text to describe template in admin site
        :param help_context: Dictionary of possible keys used in the context and description of their content
        :param subject: Default subject of email [optional]

        `help_context` items values may be strings or tuples of two strings. If strings, then email template preview
        will use variable names to fill context, otherwise the second tuple element will become example value.

        If an email template is already registered, this will raise AlreadyRegistered.
        """
        if path in self._registry:
            raise AlreadyRegistered("The template %s is already registered" % path)
        self._registry[path] = RegistrationItem(
            path, help_text, help_context, name=name, subject=subject
        )
        logger.debug("Registered email template %s", path)

    def is_registered(self, path):
        return path in self._registry

    def get_registration(self, path):
        """
        Returns registration item for specified path.

        If an email template is not registered, this will raise NotRegistered.
        """
        if not self.is_registered(path):
            raise NotRegistered("Email template not registered")
        return self._registry[path]

    def get_name(self, path):
        return self.get_registration(path).name

    def get_help_text(self, path):
        return self.get_registration(path).help_text

    def get_help_context(self, path):
        return self.get_registration(path).help_context

    def get_help_content(self, path):
        return self.get_registration(path).get_help_content()

    def get_subject(self, path):
        return self.get_registration(path).subject

    def registration_items(self):
        return self._registry.values()

    def email_template_choices(self):
        """
        Returns list of choices that can be used in email template form field choices.
        """
        return [item.as_form_choice() for item in self.registration_items()]

    def get_form_help_text(self, path):
        """
        Returns text that can be used as form help text for creating email templates.
        """
        try:
            form_help_text = render_to_string(
                "admin/emailtemplates/_helptext.html",
                context={"registration_item": self.get_registration(path)},
            )
        except NotRegistered:
            form_help_text = ""
        return form_help_text


# Global object for singleton registry of email templates
email_templates = EmailTemplateRegistry()
