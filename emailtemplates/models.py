# coding=utf-8
import logging
import os
import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template import TemplateDoesNotExist
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from emailtemplates.helpers import TemplateSourceLoader, mass_mailing_recipients
from emailtemplates.managers import EmailLogManager, EmailLogQuerySet
from emailtemplates.registry import NotRegistered, email_templates

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime

    now = datetime.now

logger = logging.getLogger(__name__)

# `{% extends %}` must be the very first tag of a template, so content using it cannot be
# wrapped in a layout. Such content is left untouched, see `EmailTemplate.get_content()`.
EXTENDS_TAG_RE = re.compile(r"{%\s*extends[\s%]")
HEAD_END_RE = re.compile(r"</head\s*>", re.IGNORECASE)


def _normalize(content):
    """
    Content compared regardless of whitespace and line endings.
    """
    return " ".join((content or "").split())


class EmailLayout(models.Model):
    """
    Reusable frame for emails: everything that should surround the content of an email
    template, e.g. a header with a logo and a footer with company data.

    An email using a layout is rendered as:
    `<style>styles</style>` + `header_content` + `EmailTemplate.content` + `footer_content`.

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
    styles = models.TextField(
        _("CSS styles"),
        blank=True,
        help_text=_(
            "Plain CSS, without the &lt;style&gt; tag - it is added automatically and "
            "placed before the header."
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

    def styles_tag(self):
        """
        `styles` wrapped in a <style> tag, empty string when no styles are defined.
        """
        if not self.styles.strip():
            return ""
        return f'<style type="text/css">{self.styles}</style>'

    def wrap_content(self, content):
        """
        Returns given content surrounded by the styles, header and footer of this layout.

        The styles go before the header, or into it, before </head>, when the header is
        the start of a whole HTML document.
        """
        header = self.header_content
        styles = self.styles_tag()
        head_end = HEAD_END_RE.search(header)
        if styles and head_end:
            header = header[: head_end.start()] + styles + header[head_end.start() :]
            styles = ""
        return "".join((styles, header, content, self.footer_content))


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
    preheader = models.CharField(
        _("preheader"),
        max_length=255,
        blank=True,
        help_text=_(
            "Short text shown by email clients next to the subject in the inbox, available "
            "to the layout as {{ preheader }}. You can use variables from table."
        ),
    )
    content = models.TextField(_("content"))
    default_content = models.TextField(
        _("default content"),
        blank=True,
        editable=False,
        help_text=_(
            "The template file as it was when the content was created or last replaced "
            "with it. A different file means a new default version is available."
        ),
    )
    previous_content = models.TextField(
        _("previous content"),
        blank=True,
        editable=False,
        help_text=_(
            "The content before it was last replaced with the default version."
        ),
    )
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
        except TemplateDoesNotExist:
            # templates may live in the database only, e.g. created in the admin
            logger.debug("Email template %s has no template file.", self.title)
            return ""
        except Exception as e:
            logger.error("Error loading template %s. Details: %s ", self.title, e)
            return ""

    def get_default_subject(self):
        # the subject of the registration may be translated; in the language of the
        # template, without switching the language of the rest of the request
        with translation.override(self.language):
            try:
                return str(email_templates.get_subject(self.title))
            except NotRegistered:
                return ""

    def get_default_preheader(self):
        # in the language of the template, like the subject
        with translation.override(self.language):
            try:
                return str(email_templates.get_preheader(self.title))
            except NotRegistered:
                return ""

    def has_new_default(self):
        """
        Whether the template file changed since the content was made from it: developers
        updated the default content, which the Site Admin may take over, see
        `replace_with_default()`. Never applied by itself, the content may be edited.

        False for templates without a snapshot of the file, e.g. those having no template
        file when they were created or migrated to 3.0.0.
        """
        if not self.default_content:
            return False
        default = self.get_default_content()
        return bool(default) and _normalize(default) != _normalize(self.default_content)

    def differs_from_default(self):
        """
        Whether the content is not the current template file.
        """
        default = self.get_default_content()
        return bool(default) and _normalize(default) != _normalize(self.content)

    def replace_with_default(self):
        """
        Takes over the current template file as the content, keeping the content it
        replaces in `previous_content`, see `restore_previous_content()`.
        """
        default = self.get_default_content()
        self.previous_content = self.content
        self.content = default
        self.default_content = default
        self.save()

    def restore_previous_content(self):
        """
        Undoes `replace_with_default()`; the replaced content becomes the previous one.
        """
        self.content, self.previous_content = self.previous_content, self.content
        self.save()

    def save(self, *args, **kwargs):
        if not self.pk and not self.default_content:
            # the snapshot `has_new_default()` compares the template file with
            self.default_content = self.get_default_content()
        if not self.content:
            self.content = self.get_default_content()
        if not self.subject:
            self.subject = self.get_default_subject()
        if not self.pk and not self.preheader:
            # only for new templates, an empty preheader may be the choice of the admin
            self.preheader = self.get_default_preheader()
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


class EmailLog(models.Model):
    """
    An outgoing email and its delivery status: the history of sent emails in the admin.

    Entries are written by the email backend (`emailtemplates.backends`) for every email
    sent through it - not only the ones of email templates - before the email is handed to
    the real backend, and marked sent or failed afterwards. Whatever sent the email
    describes itself in the `source*` fields; for a Celery task its name, id and arguments,
    so that a retry updates the entries of the run instead of adding new ones.

    `EmailFromTemplate.send_later()` writes the entry when the email is rendered and the
    email is sent with it later, see `deliver()`.

    The content (``html``, ``text``) is kept after sending unless
    ``EMAILTEMPLATES_EMAIL_LOG_CONTENT = False``; attachments are kept by name only.
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    STATUSES = (
        (PENDING, _("pending")),
        (SENT, _("sent")),
        (FAILED, _("failed")),
    )

    id = models.BigAutoField(
        auto_created=True, primary_key=True, serialize=False, verbose_name=_("ID")
    )
    status = models.CharField(
        _("status"), max_length=10, choices=STATUSES, default=PENDING
    )
    template = models.CharField(_("template"), max_length=255, blank=True)
    language = models.CharField(_("language"), max_length=10, blank=True)
    source = models.CharField(
        _("source"),
        max_length=255,
        blank=True,
        help_text=_("What sent the email, e.g. the name of a Celery task."),
    )
    source_id = models.CharField(
        _("source id"),
        max_length=255,
        blank=True,
        help_text=_(
            "The run of the source that sent the email, e.g. the id of a Celery task; "
            "emails sharing it come from one run."
        ),
    )
    source_seq = models.PositiveSmallIntegerField(
        _("source sequence"),
        default=0,
        help_text=_("The position of the email among the emails of one run."),
    )
    source_context = models.JSONField(
        _("source context"),
        default=dict,
        blank=True,
        help_text=_("What the source was called with, e.g. the arguments of a task."),
    )
    subject = models.CharField(_("subject"), max_length=998, blank=True)
    from_email = models.CharField(_("from"), max_length=255, blank=True)
    recipients = models.JSONField(_("recipients"), default=list)
    cc = models.JSONField(_("cc"), default=list, blank=True)
    bcc = models.JSONField(_("bcc"), default=list, blank=True)
    reply_to = models.JSONField(_("reply to"), default=list, blank=True)
    headers = models.JSONField(_("headers"), default=dict, blank=True)
    html = models.TextField(_("HTML"), blank=True)
    text = models.TextField(_("plain text"), blank=True)
    # the file names
    attachments = models.JSONField(_("attachments"), default=list, blank=True)
    attempts = models.PositiveSmallIntegerField(
        _("attempts"),
        default=0,
        help_text=_("How many times the email was handed to the email backend."),
    )
    last_error = models.TextField(_("last error"), blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    created = models.DateTimeField(_("created"), default=now)
    modified = models.DateTimeField(_("modified"), auto_now=True)

    objects = EmailLogManager.from_queryset(EmailLogQuerySet)()

    class Meta:
        verbose_name = _("Email log")
        verbose_name_plural = _("Email logs")
        ordering = ("-created",)
        indexes = [
            models.Index(
                fields=["status", "created"], name="emailtemplates_status_idx"
            ),
            models.Index(
                fields=["source_id", "source_seq"], name="emailtemplates_source_idx"
            ),
        ]

    def __str__(self):
        return "%s -> %s (%s)" % (
            self.subject,
            ", ".join(self.recipients),
            self.get_status_display(),
        )

    def can_resend(self):
        """
        Only a failed email can be sent again, not a pending one: it may still be retried
        by the run that sends it, and sending it again would send it twice.
        """
        return self.status == self.FAILED

    def mark_sent(self):
        self.status = self.SENT
        self.sent_at = now()
        self.last_error = ""
        update_fields = ["status", "sent_at", "last_error", "modified"]
        if not getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_CONTENT", True):
            self.html = self.text = ""
            update_fields += ["html", "text"]
        self.save(update_fields=update_fields)

    def mark_failed(self, error):
        self.status = self.FAILED
        self.last_error = str(error)
        self.save(update_fields=["status", "last_error", "modified"])

    def get_message(self, attachments=()):
        """
        The email of this entry: an `EmailMultiAlternatives` with the plain text as its body
        and the HTML as its alternative, which the email backend records in this entry.
        `attachments` - (filename, content[, mimetype]) tuples.
        """
        message = EmailMultiAlternatives(
            subject=self.subject,
            body=self.text,
            from_email=self.from_email or None,
            to=self.recipients,
            cc=self.cc,
            bcc=self.bcc,
            reply_to=self.reply_to,
            headers=self.headers,
            attachments=list(attachments),
        )
        if self.html:
            message.attach_alternative(self.html, "text/html")
        message.email_log = self
        message.email_template = self.template
        message.email_language = self.language
        return message

    def deliver(self, attachments=(), fail_silently=False):
        """
        Sends the email of this entry now. The email backend of emailtemplates records the
        attempt and its result here; with another backend this entry records them itself.
        Returns the number of emails sent.
        """
        message = self.get_message(attachments)
        try:
            sent = message.send(fail_silently=fail_silently)
        except Exception as e:
            if not getattr(message, "email_log_recorded", False):
                self.count_attempt()
                self.mark_failed("%s: %s" % (type(e).__name__, e))
            raise
        if not getattr(message, "email_log_recorded", False):
            self.count_attempt()
            if sent:
                self.mark_sent()
            else:
                self.mark_failed("The email was not sent.")
        return sent

    def count_attempt(self):
        EmailLog.objects.filter(pk=self.pk).update(attempts=models.F("attempts") + 1)
        self.refresh_from_db(fields=["attempts"])
