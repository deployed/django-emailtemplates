# coding=utf-8
import logging

from django.conf import settings
from django.db import models
from django.template import Engine
from django.utils.translation import ugettext_lazy as _

from emailtemplates.helpers import TemplateSourceLoader, mass_mailing_recipients

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
        unique_together = ((u'title', u'language'),)

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


class MassEmailMessage(models.Model):
    subject = models.CharField(_(u'subject'), max_length=255)
    content = models.TextField(_(u'content'))
    date_sent = models.DateTimeField(_(u'sent'), null=True, blank=True)

    def __unicode__(self):
        return self.subject

    @property
    def sent(self):
        return bool(self.date_sent)

    def send(self, recipients=None, force=False):
        from emailtemplates.email import EmailFromTemplate
        recipients = recipients or mass_mailing_recipients()
        if self.sent and not force:
            return False
        eft = EmailFromTemplate(
            name="emailtemplates/mass_email.html", subject=self.subject,
            template_object=self, registry_validation=False,
        )
        attachment_paths = [attachment.attachment_file.path for attachment in self.attachments.all()]
        sent_count = 0
        for recipient in recipients:
            sent = eft.send(to=[recipient], attachment_paths=attachment_paths)
            if sent:
                sent_count += 1
                logger.info(u"Successfully sent mass email message to user %s", recipient)
            else:
                logger.warning(u"Error sending mass email message to user %s", recipient)
        self.date_sent = now()
        self.save()
        return sent_count == len(recipients)


class MassEmailAttachment(models.Model):
    attachment_file = models.FileField(_(u"Attachment file"))
    mass_email_message = models.ForeignKey(MassEmailMessage, related_name="attachments", on_delete=models.CASCADE)
