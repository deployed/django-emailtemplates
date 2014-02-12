# coding=utf-8
import os

from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime
    now = datetime.now


def get_template_choices(suffix='.html'):
    """
    returns list of html templates from emailtemplates/*/
    """
    FUNCLIST_CHOICES = []
    path = os.path.join(settings.TEMPLATE_DIRS[0], "emailtemplates")
    for root, dirs, files in os.walk(path):
        for name in files:
            filename = os.path.join(root, name).replace(path, '')
            if filename.endswith(suffix):
                FUNCLIST_CHOICES.append([filename[1:], filename[1:]])
    return FUNCLIST_CHOICES


class EmailTemplate(models.Model):
    """
    Model to store email template.
    """
    title = models.CharField(_(u'template'), max_length=255, choices=get_template_choices())
    subject = models.CharField(_(u'subject'), max_length=255, blank=True)
    content = models.TextField(_(u'content'))
    language = models.CharField(_(u'language'), max_length=10, choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)
    created = models.DateTimeField(default=now)
    modified = models.DateTimeField(default=now)

    class Meta:
        unique_together = (('title', 'language'),)

    def __unicode__(self):
        return u'%s -> %s' % (self.title, self.language)
