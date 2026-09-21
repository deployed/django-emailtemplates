# coding=utf-8
import logging
import os
import re

from django.conf import settings
from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from emailtemplates.helpers import TemplateSourceLoader, mass_mailing_recipients
from emailtemplates.registry import email_templates, NotRegistered

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime

    now = datetime.now

logger = logging.getLogger(__name__)

# `{% extends %}` must be the very first tag of a template, so content using it cannot be
# wrapped in a layout. Such content is left untouched, see `EmailTemplate.get_content()`.
EXTENDS_TAG_RE = re.compile(r"{%\s*extends[\s%]")


class EmailLayout(models.Model):
    """
    Reusable frame for emails: everything that should surround the content of an email
    template, e.g. a header with a logo and a footer with company data.

    An email using a layout is rendered as:
    `header_content` + `EmailTemplate.content` + `footer_content`.

    All three parts are rendered together, as one Django template and with one context, so
    the header and the footer may use the same context variables as the email template.
    """

    name = models.CharField(_("name"), max_length=255, unique=True)
    header_content = models.TextField(
        _("header content"),
        blank=True,
        help_text=_(
            "Rendered above the content of every email template using this layout."
        ),
    )
    footer_content = models.TextField(
        _("footer content"),
        blank=True,
        help_text=_(
            "Rendered below the content of every email template using this layout."
        ),
    )
    created = models.DateTimeField(_("created"), auto_now_add=True)
    modified = models.DateTimeField(_("modified"), auto_now=True)

    class Meta:
        verbose_name = _("Email layout")
        verbose_name_plural = _("Email layouts")
        ordering = ("name",)

    def __str__(self):
        return self.name

    def wrap_content(self, content):
        """
        Returns given content surrounded by the header and the footer of this layout.
        """
        return "".join((self.header_content, content or "", self.footer_content))


class EmailTemplate(models.Model):
    """
    Model to store email template.
    """

    id = models.BigAutoField(
        auto_created=True, primary_key=True, serialize=False, verbose_name=_("ID")
    )
    title = models.CharField(_("template"), max_length=255)
    subject = models.CharField(
        _("subject"),
        max_length=255,
        blank=True,
        help_text=_("you can use variables from table"),
    )
    content = models.TextField(_("content"))
    layout = models.ForeignKey(
        "EmailLayout",
        verbose_name=_("layout"),
        related_name="email_templates",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        help_text=_(
            "Optional. When set, the content above is rendered between the header and the "
            "footer of the chosen layout."
        ),
    )
    language = models.CharField(
        _("language"),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    ordering = models.PositiveIntegerField(verbose_name=_("ordering"), default=1)
    attachments = models.ManyToManyField(
        "EmailAttachment", blank=True, verbose_name=_("attachments")
    )
    created = models.DateTimeField(default=now, verbose_name=_("created"))
    modified = models.DateTimeField(default=now, verbose_name=_("modified"))

    class Meta:
        unique_together = (("title", "language"),)
        verbose_name = _("Email template")
        verbose_name_plural = _("Email templates")
        ordering = ("ordering",)

    def __str__(self):
        return "%s -> %s" % (self.title, self.language)

    def get_content(self):
        """
        Content to render: wrapped in the selected layout, if there is one.

        Content that uses `{% extends %}` brings its own frame and cannot be wrapped (the tag
        must stay the first one in a template), so it is returned as it is. The admin form
        rejects that combination, this is only a safety net for data created another way.
        """
        if not self.layout_id:
            return self.content
        if EXTENDS_TAG_RE.search(self.content or ""):
            logger.warning(
                "Email template %s uses {%% extends %%}, layout %s will be ignored.",
                self.title,
                self.layout_id,
            )
            return self.content
        return self.layout.wrap_content(self.content)

    def get_default_content(self):
        loader = TemplateSourceLoader()
        try:
            return loader.get_source(self.title)
        except Exception as e:
            logger.error("Error loading template %s. Details: %s ", self.title, e)
            return ""

    def get_default_subject(self):
        translation.activate(self.language)
        try:
            return email_templates.get_subject(self.title)
        except NotRegistered:
            return ""

    def save(self, *args, **kwargs):
        if not self.content:
            self.content = self.get_default_content()
        if not self.subject:
            self.subject = self.get_default_subject()
        super(EmailTemplate, self).save(*args, **kwargs)


class BaseEmailAttachment(models.Model):
    id = models.BigAutoField(
        auto_created=True, primary_key=True, serialize=False, verbose_name=_("ID")
    )
    name = models.CharField(_("name"), blank=True, max_length=50)
    attachment_file = models.FileField(
        _("Attachment file"), upload_to="emails/attachments/", max_length=255
    )
    comment = models.TextField(
        verbose_name=_("Comment"), blank=True, help_text=_("visible only in admin")
    )
    ordering = models.PositiveIntegerField(verbose_name=_("Ordering"), default=0)
    send_as_link = models.BooleanField(verbose_name=_("Send as link"), default=True)

    class Meta:
        abstract = True
        ordering = ["ordering"]
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
    id = models.BigAutoField(
        auto_created=True, primary_key=True, serialize=False, verbose_name=_("ID")
    )
    subject = models.CharField(_("subject"), max_length=255)
    content = models.TextField(_("content"))
    date_sent = models.DateTimeField(_("sent"), null=True, blank=True)

    class Meta:
        verbose_name = _("Mass email message")
        verbose_name_plural = _("Mass email messages")

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
            name="emailtemplates/mass_email.html",
            subject=self.subject,
            template_object=self,
            registry_validation=False,
        )
        attachment_paths = [
            attachment.attachment_file.path for attachment in self.attachments.all()
        ]
        sent_count = 0
        for recipient in recipients:
            sent = eft.send(to=[recipient], attachment_paths=attachment_paths)
            if sent:
                sent_count += 1
                logger.info(
                    "Successfully sent mass email message to user %s", recipient
                )
            else:
                logger.warning("Error sending mass email message to user %s", recipient)
        self.date_sent = now()
        self.save()
        return sent_count == len(recipients)


class MassEmailAttachment(BaseEmailAttachment):
    mass_email_message = models.ForeignKey(
        MassEmailMessage, related_name="attachments", on_delete=models.CASCADE
    )
