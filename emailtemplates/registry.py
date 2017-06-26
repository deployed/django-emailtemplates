# coding=utf-8


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


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
        self._registry[path] = (help_text, help_context)

    def get_email_template(self, path):
        if path not in self._registry:
            raise NotRegistered("Email template not registered")
        return self._registry[path]

    def get_help_text(self, path):
        return self.get_email_template(path)[0]

    def get_help_context(self, path):
        return self.get_email_template(path)[1]

    def get_email_templates(self):
        return self._registry

    def get_email_template_names(self):
        return self._registry.keys()


# Global object for singleton registry of email templates
email_templates = EmailTemplateRegistry()
