# coding=utf-8
import os
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _


try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime

    now = datetime.now


class EmailTemplate(models.Model):
    """
    Model to store email template.
    """
    title = models.CharField(_(u'template'), max_length=255)
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
