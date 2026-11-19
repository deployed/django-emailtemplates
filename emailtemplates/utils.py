# coding=utf-8
import copy
import logging
from contextlib import contextmanager

from django.http import HttpResponse
from django.utils.html import escape, format_html

from .email import EmailFromTemplate
from .registry import email_templates

logger = logging.getLogger(__name__)


@contextmanager
def suppress_and_log(*exceptions, message):
    """
    Like `contextlib.suppress`, but logs the exception, with its traceback; any exception
    when none is given. For the history of sent emails, which must never stop an email.
    """
    try:
        yield
    except exceptions or Exception:
        logger.exception(message)


def render_preview(email_template, content=None):
    """
    HTML of the preview of an email template: `content` (by default the content of the
    template) rendered by `EmailFromTemplate` as the email is sent - in the layout, with the
    subject, the preheader and the blocks - filled with the example context of the registry.
    """
    if content is not None:
        email_template = copy.copy(email_template)
        email_template.content = content
    eft = EmailFromTemplate(
        name=email_template.title,
        language=email_template.language,
        template_object=email_template,
        registry_validation=False,
    )
    eft.context.update(email_templates.get_preview_context(email_template.title))
    return eft.render().html


def sandboxed_response(html):
    """
    HTML written in the admin, in an <iframe sandbox> filling the page: without scripts
    and on an origin of its own, as the other previews show it.
    """
    return HttpResponse(
        format_html(
            '<!DOCTYPE html><meta charset="utf-8"><style>html, body, iframe '
            "{{margin: 0; border: 0; width: 100%; height: 100%; display: block}}"
            '</style><iframe sandbox srcdoc="{}"></iframe>',
            # rendered templates are marked safe, escape() escapes them anyway
            escape(html),
        ),
        content_type="text/html; charset=utf-8",
    )
