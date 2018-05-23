# coding=utf-8
from string import lower

from django.template.loaders import app_directories
from django.contrib.auth import get_user_model


class SubstringMatcher(object):
    """
    Class to be used with Mock() in order not to supply full content
    of the argument (e.g. for logger).
    Based on: http://www.michaelpollmeier.com/python-mock-how-to-assert-a-substring-of-logger-output/

    Usage with this class aliased to substr:
    email_logger.warning.assert_called_with(substr("Can't find EmailTemplate object in database"))

    This would do the same, but requires exactly the same argument content:
    email_logger.warning.assert_called_with("Can't find EmailTemplate object in database, using default file template.")
    """

    def __init__(self, containing):
        self.containing = lower(containing)

    def __eq__(self, other):
        return lower(other).find(self.containing) > -1

    def __unicode__(self):
        return 'a string containing "%s"' % self.containing

    def __str__(self):
        return unicode(self).encode('utf-8')

    __repr__ = __unicode__


substr = SubstringMatcher


class TemplateSourceLoader(app_directories.Loader):
    def get_source(self, template_name):
        source, origin = self.load_template_source(template_name)
        return source


def mass_mailing_recipients():
    """
    Returns iterable of all mass email recipients.
    Default behavior will be to return list of all active users' emails.
    This can be changed by providing callback in settings return some other list of users,
    when user emails are stored in many, non default models.

    :rtype iterable
    """
    User = get_user_model()
    if hasattr(User, 'is_active') and hasattr(User, 'email'):
        return User.objects.filter(is_active=True).values_list('email', flat=True).distinct()
    return []
