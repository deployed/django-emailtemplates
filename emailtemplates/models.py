# coding=utf-8
import logging

from django.conf import settings
from django.db import models
from django.template import Engine
from django.utils.translation import ugettext_lazy as _

from emailtemplates.helpers import TemplateSourceLoader

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime

    now = datetime.now

logger = logging.getLogger(__name__)


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

    def get_default_content(self):
        engine = Engine.get_default()
        loader = TemplateSourceLoader(engine)
        try:
            return loader.get_source(self.title)
        except Exception as e:
            logger.error('Error loading template %s. Details: %s ', self.title, e)
            return ''

    def save(self, *args, **kwargs):
        if not self.content:
            self.content = self.get_default_content()
        super(EmailTemplate, self).save(*args, **kwargs)
