# coding=utf-8
import logging


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


class EmailTemplateRegistry(object):

    def __init__(self):
        self._registry = {}

    def register(self, path, help_text=None, help_context=None):
        """
        Registers email template.

        Example usage:
            email_templates.register('hello_template.html', help_text=u'Hello template',
                help_context={'username': u'Name of user in hello expression'})

        :param path: Template file path relative to prefix
        :param help_text: Help text to describe template in admin site
        :param help_context: Dictionary of possible keys used in the context and description of their content

        If a model is already registered, this will raise AlreadyRegistered.
        """
        if path in self._registry:
            raise AlreadyRegistered('The template %s is already registered' % path)
        self._registry[path] = RegistrationItem(path, help_text, help_context)
        logger.debug("Registered email template %s", path)

    def is_registered(self, path):
        return path in self._registry

    def _get_registration(self, path):
        if not self.is_registered(path):
            raise NotRegistered("Email template not registered")
        return self._registry[path]

    def get_help_text(self, path):
        return self._get_registration(path).help_text

    def get_help_context(self, path):
        return self._get_registration(path).help_context

    def get_email_template_choices(self):
        return [(template_name, template_name) for template_name in list(set(self._registry.keys()))]

    def get_context_description(self, path):
        help_context = self.get_help_context(path) or {}
        return u", ".join([u"%s (%s)" % (k, v) for (k, v) in help_context.items()])

    def get_admin_help_text_information(self, path):
        return u"USAGE: %s \nCONTEXT: %s" % (self.get_help_text(path), self.get_context_description(path))

    def create_eft(self, path, *args, **kwargs):
        if self._get_registration(path):
            return


# Global object for singleton registry of email templates
email_templates = EmailTemplateRegistry()
