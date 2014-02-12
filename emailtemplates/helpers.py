# coding=utf-8
from string import lower


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
