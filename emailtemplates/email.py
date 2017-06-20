# coding=utf-8
import os
import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.template import Template, Context, TemplateDoesNotExist
from django.template.loader import get_template

from .models import now, EmailTemplate


logger = logging.getLogger(__name__)


class EmailFromTemplate(object):
    """
    EmailFromTemplate class tries to load template from database. If template object is not found,
    it tries to load template from templates/emailtemplates/{{prefix}} directory.
    This enables developers to create default templates for emails that are sent,
    and Site Admins to easily override the templates and provide email translations.

    Site Admins should know given template context.
    Site Admins should be familiar with Django Template System.
    """
    def __init__(self,
                 name="",
                 from_email=settings.DEFAULT_FROM_EMAIL,
                 language=settings.LANGUAGE_CODE,
                 subject="",
                 prefix="",
                 template_class=EmailTemplate
    ):
        """
        Class constructor

        @param name: template name
        @param from_email: sender email address, by default settings.DEFAULT_FROM_EMAIL
        @param language: email language, by default settings.LANGUAGE_CODE
        @param subject: subject of the email
        @param prefix: folder, where templates are stored (e.g. prefix 'email' and name 't.htm' will search email/t.htm)
        @param template_class: class, template objects will be retrieved from

        By default 'date' context variable is filled in.
        """
        self.from_email = from_email
        self.template_class = template_class
        self.subject = subject
        self.language = language
        self.name = name
        self.prefix = prefix

        self.template = None
        self.compiled_template = None  # for storing compiled template
        self.context = {'date': now()}  # default context
        self.sent = 0  # number of messages sent
        self.message = ""
        self.content_subtype = 'html'
        self._template_source = 'default'

    @property
    def template_source(self):
        """Source of the template. One of the following:
           * default
           * filesystem
           * database
        """
        return self._template_source

    def __get_path(self):
        return os.path.join(self.prefix, self.name)

    def __get_template_from_file(self):
        path = self.__get_path()
        try:
            self.compiled_template = get_template(path)
        except TemplateDoesNotExist:
            logger.warning("Can't find %s template in the filesystem, will use very default one." % path)
        else:
            self._template_source = 'filesystem'

    def get_object(self):
        language = self.language
        while True:
            try:
                tmp = self.template_class.objects.get(title=self.name, language=language)
            except ObjectDoesNotExist:
                logger.warning("Can't find EmailTemplate object in database, using default file template.")
                break
            except UnicodeError:
                logger.warning(
                    "Can't convert to unicode EmailTemplate object from database, using default file template.")
                break
            else:
                self.template = unicode(tmp.content)
                self.subject = unicode(tmp.subject) or self.subject
                self._template_source = 'database'
                logger.debug(u"Got template %s from database" % self.name)
                return
        # fallback
        self.__get_template_from_file()

    def __compile_template(self):
        if not self.compiled_template:
            self.compiled_template = Template(self.template)

    def render_message(self):
        self.__compile_template()
        context = Context(self.context)
        self.message = self.compiled_template.render(context)

    def send_email(self, send_to, *args, **kwargs):
        """
        Sends email to recipient based on self object parameters.

        @param send_to: recipient email
        @param args: additional args passed to EmailMessage
        @param kwargs: kwargs passed to EmailMessage
        @return: number of sent messages
        """
        msg = EmailMessage(self.subject, self.message, self.from_email, send_to, *args, **kwargs)
        msg.content_subtype = self.content_subtype

        try:
            self.sent = msg.send()
        except SMTPException, e:
            logger.error(u'Problem sending email to %s: %s' % (send_to, e))

        return self.sent

    def send(self, to, *args, **kwargs):
        """This function does all the operations on eft object, that are necessary to send email.
           Usually one would use eft object like this:
                eft = EmailFromTemplate(name='sth/sth.html')
                eft.get_object()
                eft.render_message()
                eft.send_email(['email@example.com'])
                return eft.sent
        """
        self.get_object()
        self.render_message()
        self.send_email(to, *args, **kwargs)
        logger.info(u"Mail has been sent to: %s " % to)
        return self.sent
