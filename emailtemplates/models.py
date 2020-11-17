# coding=utf-8
import logging
import os

from django.conf import settings
from django.db import models
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
    attachments = models.ManyToManyField("EmailAttachment", blank=True, verbose_name=_("attachments"))
    created = models.DateTimeField(default=now, verbose_name=_("created"))
    modified = models.DateTimeField(default=now, verbose_name=_("modified"))

    class Meta:
        unique_together = (('title', 'language'),)
        verbose_name = _('Email template')
        verbose_name_plural = _('Email templates')

    def __str__(self):
        return '%s -> %s' % (self.title, self.language)

    def get_default_content(self):
        loader = TemplateSourceLoader()
        try:
            return loader.get_source(self.title)
        except Exception as e:
            logger.error('Error loading template %s. Details: %s ', self.title, e)
            return ''

    def save(self, *args, **kwargs):
        if not self.content:
            self.content = self.get_default_content()
        super(EmailTemplate, self).save(*args, **kwargs)


class BaseEmailAttachment(models.Model):
    name = models.CharField(_("name"), blank=True, max_length=50)
    attachment_file = models.FileField(_(u"Attachment file"), upload_to="emails/attachments/")

    class Meta:
        abstract = True
        verbose_name = _("Attachment")
        verbose_name_plural = _("Attachments")

    def __str__(self):
        return _("Attachment: %s") % self.get_name()

    def get_name(self):
        return self.name or os.path.basename(self.attachment_file.name)


class EmailAttachment(BaseEmailAttachment):
    pass

    # email_template = models.ForeignKey(EmailTemplate, verbose_name=_('email template'), on_delete=models.CASCADE)


class MassEmailMessage(models.Model):
    subject = models.CharField(_(u'subject'), max_length=255)
    content = models.TextField(_(u'content'))
    date_sent = models.DateTimeField(_(u'sent'), null=True, blank=True)

    class Meta:
        verbose_name = _('Mass email message')
        verbose_name_plural = _('Mass email messages')

    def __str__(self):
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


class MassEmailAttachment(BaseEmailAttachment):
    mass_email_message = models.ForeignKey(MassEmailMessage, related_name="attachments", on_delete=models.CASCADE)
