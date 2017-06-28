# coding=utf-8
import logging
from django.utils.translation import ugettext_lazy as _


logger = logging.getLogger(__name__)


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class RegistrationItem(object):

    def __init__(self, path, help_text=None, help_context=None):
        self.path = path
        self.help_text = help_text or u""
        self.help_context = help_context or {}

    def context_description(self):
        help_text_item = lambda k, v: u"%s (%s)" % (k, v) if v else u"%s" % k
        return u", ".join([help_text_item(k, v) for (k, v) in self.help_context.items()])

    def as_form_help_text(self):
        item_help_text = _(u"USAGE: %s") % self.help_text if self.help_text else u""
        item_help_context = _(u"CONTEXT: %s") % self.context_description() if self.help_context else u""
        return u"%s | %s" % (item_help_text, item_help_context)

    def as_form_choice(self):
        return self.path, self.path


class EmailTemplateRegistry(object):

    def __init__(self):
        self._registry = {}

    def register(self, path, help_text=None, help_context=None):
        """
        Registers email template.

        Example usage:
            email_templates.register('hello_template.html', help_text=u'Hello template',
                help_context={'username': u'Name of user in hello expression'})

        :param path: Template file path. It will become immutable registry lookup key.
        :param help_text: Help text to describe template in admin site
        :param help_context: Dictionary of possible keys used in the context and description of their content

        If an email template is already registered, this will raise AlreadyRegistered.
        """
        if path in self._registry:
            raise AlreadyRegistered('The template %s is already registered' % path)
        self._registry[path] = RegistrationItem(path, help_text, help_context)
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

    def get_help_text(self, path):
        return self.get_registration(path).help_text

    def get_help_context(self, path):
        return self.get_registration(path).help_context

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
            form_help_text = self.get_registration(path).as_form_help_text()
        except NotRegistered:
            form_help_text = u""
        return form_help_text


# Global object for singleton registry of email templates
email_templates = EmailTemplateRegistry()
