# coding=utf-8
"""
Attachments of sent emails, see `emailtemplates.models.EmailLog`.

The attachments of an email added by code (e.g. an invoice made for its recipient) are kept
with its `EmailLog` as files, so that a failed email can be sent again with them; the
attachments of its email template are taken from the template again instead. Settings:

* ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS`` - ``False`` keeps none (``True`` by default).
* ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS`` - after how many days the files of
  sent emails are deleted by ``cleanup_email_logs``; ``0`` deletes them once the email is
  sent; ``None`` (the default) keeps them as long as the email log.
* ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_STORAGE`` - the alias of the storage of ``STORAGES``
  for the files, e.g. a private one; the default storage by default.
"""

import base64
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.timezone import now


def attachments_enabled():
    return getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS", True)


def attachment_retention_days():
    return getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS", None)


def attachment_storage():
    alias = getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_STORAGE", None)
    if not alias:
        return default_storage
    from django.core.files.storage import storages

    return storages[alias]


def attachment_upload_to(instance, filename):
    """
    A random name, so that the file - often with personal data - cannot be guessed.
    """
    extension = os.path.splitext(filename)[1]
    return "emailtemplates/email_logs/%s/%s%s" % (
        now().strftime("%Y/%m/%d"),
        uuid.uuid4().hex,
        extension,
    )


def message_attachments(message):
    """
    The attachments of `message` as (filename, content, mimetype) triples, MIME parts
    included, so that they can be attached to an email again.
    """
    attachments = []
    for attachment in message.attachments:
        if isinstance(attachment, tuple):
            attachments.append(tuple(attachment))
        else:  # a MIME part, e.g. attached with message.attach(mime_part)
            attachments.append(
                (
                    attachment.get_filename(),
                    attachment.get_payload(decode=True),
                    attachment.get_content_type(),
                )
            )
    return attachments


def code_attachments(message):
    """
    The attachments of `message` added by code, not by its email template: `EmailFromTemplate`
    marks the names of the attachments of the template, see `get_message_object()`.
    """
    template_names = set(getattr(message, "email_template_attachments", ()))
    return [
        attachment
        for attachment in message_attachments(message)
        if attachment[0] not in template_names
    ]


def store_attachments(email_log, message):
    """
    Keeps the attachments of `message` added by code with `email_log`, replacing the ones
    an earlier attempt of the email kept, see ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS``.
    """
    if not attachments_enabled():
        return
    email_log.attachment_files.all().delete()
    for attachment in code_attachments(message):
        keep_attachment(email_log, *attachment)


def keep_attachment(email_log, filename, content, mimetype=None):
    """
    Keeps one attachment with `email_log` as a file.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    attachment = email_log.attachment_files.model(
        email_log=email_log, name=filename, mimetype=mimetype or ""
    )
    attachment.file.save(filename, ContentFile(content), save=True)


def encode_attachments(attachments):
    """
    `attachments` as JSON for the Celery task: [filename, base64 content, mimetype] lists.
    """
    encoded = []
    for filename, content, *mimetype in attachments:
        if isinstance(content, str):
            content = content.encode("utf-8")
        encoded.append(
            [filename, base64.b64encode(content).decode("ascii"), *mimetype[:1]]
        )
    return encoded


def decode_attachments(encoded):
    """
    Reverts `encode_attachments()`.
    """
    return [
        (filename, base64.b64decode(content), *mimetype)
        for filename, content, *mimetype in encoded
    ]
