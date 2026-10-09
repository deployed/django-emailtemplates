# coding=utf-8
import logging
import os
import re

from django.apps import apps
from django.conf import settings
from django.db import models
from django.template import TemplateDoesNotExist
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from emailtemplates.helpers import TemplateSourceLoader, mass_mailing_recipients
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


def rich_text_available():
    """
    The rich text editor is opted into with ``EMAILTEMPLATES_RICH_TEXT = True`` and needs
    django-tinymce, see `emailtemplates.rich_text`. Without it the content is edited as
    HTML code only, so projects having django-tinymce for other reasons keep that editor.
    """
    return getattr(settings, "EMAILTEMPLATES_RICH_TEXT", False) and apps.is_installed(
        "tinymce"
    )


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

        False for templates without a snapshot of the file (created before 3.0.0).
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
