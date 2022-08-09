# coding=utf-8
import logging
import os
import re
from smtplib import SMTPException
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.template import Template, Context, TemplateDoesNotExist
from django.template.loader import get_template

from .models import now, EmailTemplate
from .registry import email_templates

logger = logging.getLogger(__name__)


class EmailFromTemplate(object):
    """
    EmailFromTemplate class tries to load template from database. If template object is not found,
    it tries to load template from templates/emailtemplates directory.
    This enables developers to create default templates for emails that are sent,
    and Site Admins to easily override the templates and provide email translations.

    Site Admins should know given template context.
    Site Admins should be familiar with Django Template System.
    """

    def __init__(
        self,
        name="",
        from_email=settings.DEFAULT_FROM_EMAIL,
        base_url="",
        language=settings.LANGUAGE_CODE,
        subject="",
        template_class=EmailTemplate,
        registry_validation=True,
        template_object=None,
    ):
        """
        Class constructor

        @param name: template name
        @param from_email: sender email address, by default settings.DEFAULT_FROM_EMAIL
        @param language: email language, by default settings.LANGUAGE_CODE
        @param subject: subject of the email
        @param template_class: class, template objects will be retrieved from
        @param registry_validation: if True template must be registered prior to instantiating EmailFromTemplate

        By default 'date' context variable is filled in.
        """
        if registry_validation:
            email_templates.get_registration(name)
        self.from_email = from_email
        self.template_class = template_class
        self.template_object = template_object
        self.subject = subject
        self.language = language
        self.name = name
        self.base_url = base_url or getattr(settings, "BASE_URL", "")

        self.template = None
        self.compiled_template = None  # for storing compiled template
        self.context = {"date": now()}  # default context
        self.sent = 0  # number of messages sent
        self.message = ""
        self.content_subtype = "html"
        self._template_source = "default"

    @property
    def template_source(self):
        """Source of the template. One of the following:
        * default
        * filesystem
        * database
        """
        return self._template_source

    def __get_path(self):
        return self.name

    def __get_template_from_file(self):
        path = self.__get_path()
        try:
            self.compiled_template = get_template(path)
        except (TemplateDoesNotExist, IOError):
            logger.warning(
                "Can't find %s template in the filesystem, will use very default one.",
                path,
            )
        else:
            self._template_source = "filesystem"

    def build_absolute_uri(self, url: str):
        """
        Builds an absolute URI.
        """
        absolute_http_url_re = re.compile(r"^https?://", re.I)
        if absolute_http_url_re.match(url):
            return url
        return urljoin(self.base_url, url)

    def get_template_object(self):
        if self.template_object:
            return self.template_object
        return self.template_class.objects.get(title=self.name, language=self.language)

    def get_subject(self, template):
        subject_template = str(template.subject) or self.subject
        subject = Template(subject_template).render(Context(self.get_context()))
        return subject

    def get_object(self):
        while True:
            try:
                tmp = self.get_template_object()
            except ObjectDoesNotExist:
                logger.warning(
                    "Can't find EmailTemplate object in database, using default file template."
                )
                break
            except UnicodeError:
                logger.warning(
                    "Can't convert to unicode EmailTemplate object from database, using default file template."
                )
                break
            else:
                self.template = str(tmp.content)
                self.subject = self.get_subject(tmp)
                self._template_source = "database"
                logger.debug("Got template %s from database", self.name)
                return
        # fallback
        self.__get_template_from_file()

    def __compile_template(self):
        if not self.compiled_template:
            self.compiled_template = Template(self.template)

    def get_context(self):
        self.context.update(
            {"default_attachments": self.get_default_attachments(as_links=True)}
        )
        return self.context

    def render_message(self):
        self.__compile_template()
        try:
            message = self.compiled_template.render(self.get_context())  #
        except AttributeError:
            # NOTE: for template from string Context() is still required!
            message = self.compiled_template.render(Context(self.get_context()))
        self.message = message

    def get_message_object(self, send_to, attachment_paths, *args, **kwargs):
        if kwargs.get("reply_to") is None:
            defaut_reply_to_email = getattr(settings, "DEFAULT_REPLY_TO_EMAIL", None)
            if defaut_reply_to_email:
                kwargs["reply_to"] = [defaut_reply_to_email]

        msg = EmailMessage(
            self.subject, self.message, self.from_email, send_to, *args, **kwargs
        )
        if attachment_paths:
            for path in attachment_paths:
                msg.attach_file(path)
        return msg

    def send_email(
        self, send_to, attachment_paths=None, fail_silently=True, *args, **kwargs
    ):
        """
        Sends email to recipient based on self object parameters.

        @param fail_silently: When it’s False, msg.send() will raise an smtplib.SMTPException if an error occurs.
        @param send_to: recipient email
        @param args: additional args passed to EmailMessage
        @param kwargs: kwargs passed to EmailMessage
        @param attachment_paths: paths to attachments as received by django EmailMessage.attach_file(path) method
        @return: number of sent messages
        """
        msg = self.get_message_object(send_to, attachment_paths, *args, **kwargs)
        msg.content_subtype = self.content_subtype

        try:
            self.sent = msg.send()
        except SMTPException as e:
            if not fail_silently:
                raise
            logger.error("Problem sending email to %s: %s", send_to, e)

        return self.sent

    def get_default_attachments(self, as_links=False):
        """
        Prepare default attachments data (files will be include into email as attachments)
        """
        attachments = []
        try:
            tmp = self.get_template_object()
        except ObjectDoesNotExist:
            return attachments

        for attachment in tmp.attachments.filter(send_as_link=as_links):
            if as_links:
                attachments.append(
                    (
                        attachment.get_name(),
                        self.build_absolute_uri(attachment.attachment_file.url),
                    )
                )
            else:
                attachments.append(
                    (
                        os.path.basename(attachment.attachment_file.name),
                        attachment.attachment_file.read(),
                    )
                )
        return attachments

    def send(self, to, attachment_paths=None, *args, **kwargs):
        """This function does all the operations on eft object, that are necessary to send email.
        Usually one would use eft object like this:
             eft = EmailFromTemplate(name='sth/sth.html')
             eft.get_object()
             eft.render_message()
             eft.send_email(['email@example.com'])
             return eft.sent
        """
        attachments = self.get_default_attachments(as_links=False)
        attachments.extend(kwargs.pop("attachments", []))

        self.get_object()
        self.render_message()
        self.send_email(to, attachment_paths, attachments=attachments, *args, **kwargs)
        if self.sent:
            logger.info("Mail has been sent to: %s ", to)
        return self.sent
