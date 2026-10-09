# coding=utf-8
"""
Sending email templates through django-post_office: the template is rendered here, the
mail queue of post_office only sends the result.

    from post_office import mail
    from emailtemplates.contrib.post_office import render_for_post_office

    mail.send(
        recipients=[user.email],
        priority="now",
        **render_for_post_office("emails/welcome.html", {"first_name": user.first_name})
    )

post_office itself is not imported, the returned dict holds plain values only.
"""

from django.conf import settings
from django.core.files.base import ContentFile

from emailtemplates.email import EmailFromTemplate


def render_for_post_office(name, context=None, language=None, **kwargs):
    """
    Renders the email template `name` with `context` and returns the kwargs of
    `post_office.mail.send()` describing it: `subject`, `message` (the plain text),
    `html_message` and, when the template has attachments sent as files, `attachments`.

    `language` defaults to `settings.LANGUAGE_CODE`. Other kwargs are passed to
    `EmailFromTemplate`, e.g. `subject` - the subject used when the template comes from a
    file, or `registry_validation`.

    Not included: the sender, the headers (e.g. `DEFAULT_REPLY_TO_EMAIL`) and everything
    about the delivery - these are passed to `mail.send()` directly.
    """
    eft = EmailFromTemplate(
        name=name, language=language or settings.LANGUAGE_CODE, **kwargs
    )
    eft.context.update(context or {})
    rendered = eft.render()
    message = {
        "subject": rendered.subject,
        "message": rendered.text,
        "html_message": rendered.html,
    }
    attachments = eft.get_default_attachments(as_links=False)
    if attachments:
        message["attachments"] = {
            filename: ContentFile(content) for filename, content in attachments
        }
    return message
