# coding=utf-8
"""
The history of sent emails (`emailtemplates.models.EmailLog`) beyond recording it, which
the email backend does (`emailtemplates.backends`): the attachments kept with it, sending
its emails now, later or again, and deleting old ones.

The attachments of an email added by code (e.g. an invoice made for its recipient) are
kept with its entry (`EmailLogAttachment`), so that a failed email can be sent again with
them; the attachments of its email template are taken from the template again instead.
Their content (`EmailLogAttachmentContent`) is kept in the database, once for every
distinct content - an attachment of a mass email is kept once, not once per recipient - and
is saved and deleted in the transaction of its entries. Settings:

* ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS`` - ``False`` keeps none (``True`` by default).
* ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS`` - after how many days the
  attachments of sent emails are deleted by `cleanup_email_logs()`; ``0`` deletes them once
  the email is sent; ``None`` (the default) keeps them as long as the email log.
"""

import base64
import hashlib
import logging
import os
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, models, transaction
from django.utils.timezone import now

from .managers import (  # noqa: F401 - importable from here with the rest
    DEFAULT_ATTACHMENT_NAME,
    attachment_name,
    message_attachments,
)
from .models import (
    EmailLog,
    EmailLogAttachment,
    EmailLogAttachmentContent,
    EmailTemplate,
)

logger = logging.getLogger(__name__)


def attachments_enabled():
    return getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS", True)


def attachment_retention_days():
    return getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS", None)


def celery_enabled():
    return getattr(settings, "EMAILTEMPLATES_CELERY", False)


def as_bytes(content):
    return content.encode("utf-8") if isinstance(content, str) else content


def code_attachments(message):
    """
    The attachments of `message` added by code, not by its email template: `EmailFromTemplate`
    marks the attachments of the template, see `get_message_object()`. Told apart by name
    and content, so that a file of the code named like a file of the template is kept.
    """
    template = Counter(
        (name, as_bytes(content))
        for name, content in getattr(message, "email_template_attachments", ())
    )
    attachments = []
    for name, content, mimetype in message_attachments(message):
        key = (name, as_bytes(content))
        if template[key]:
            template[key] -= 1
        else:
            attachments.append((name, content, mimetype))
    return attachments


def template_kept_attachments(email_log):
    """
    The attachments (`EmailAttachment`) of the email template of `email_log` sent as files,
    see `EmailFromTemplate.get_default_attachments()`.
    """
    email_template = EmailTemplate.objects.filter(
        title=email_log.template, language=email_log.language
    ).first()
    if email_template is None:
        return []
    return list(email_template.attachments.filter(send_as_link=False))


def template_attachments(email_log):
    """
    The attachments of the email template of `email_log`: (filename, content) pairs.
    """
    attachments = []
    for attachment in template_kept_attachments(email_log):
        with attachment.attachment_file.open("rb") as file:
            attachments.append(
                (os.path.basename(attachment.attachment_file.name), file.read())
            )
    return attachments


def kept_attachments(email_log):
    """
    The attachments added by code kept with `email_log`: (filename, content, mimetype)
    triples.
    """
    return [
        (attachment.name, bytes(attachment.content.data), attachment.mimetype or None)
        for attachment in email_log.kept_attachments.select_related("content")
    ]


def missing_attachments(email_log):
    """
    The names of the attachments `email_log` was sent with that cannot be attached again:
    neither kept nor attachments of its email template - e.g. deleted after the retention,
    or entries imported from elsewhere.
    """
    available = Counter(
        os.path.basename(attachment.attachment_file.name)
        for attachment in template_kept_attachments(email_log)
    )
    available.update(email_log.kept_attachments.values_list("name", flat=True))
    missing = []
    for name in email_log.attachments:
        name = attachment_name(name)  # an entry may have been recorded without one
        if available[name]:
            available[name] -= 1
        else:
            missing.append(name)
    return missing


def content_id(content):
    """
    The id of the `EmailLogAttachmentContent` of `content`, saved unless it already is.
    """
    sha256 = hashlib.sha256(content).hexdigest()
    contents = EmailLogAttachmentContent.objects.values_list("pk", flat=True)
    pk = contents.filter(sha256=sha256).first()
    if pk is not None:
        return pk
    try:
        with transaction.atomic():
            return EmailLogAttachmentContent.objects.create(
                sha256=sha256, data=content, size=len(content)
            ).pk
    except IntegrityError:  # saved meanwhile for another email
        return contents.get(sha256=sha256)


def keep_attachments(email_log, attachments):
    """
    Keeps `attachments` - (filename, content[, mimetype]) tuples - with `email_log`, all of
    them or none.
    """
    with transaction.atomic():
        for filename, content, *mimetype in attachments:
            mimetype = mimetype[0] if mimetype else None
            EmailLogAttachment.objects.create(
                email_log=email_log,
                name=attachment_name(filename, mimetype),
                mimetype=mimetype or "",
                content_id=content_id(as_bytes(content)),
            )


def store_attachments(email_log, message):
    """
    Keeps the attachments of `message` added by code with `email_log`, replacing the ones
    an earlier attempt of the email kept, see ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS``.
    """
    if not attachments_enabled():
        return
    with transaction.atomic():
        email_log.kept_attachments.all().delete()
        keep_attachments(email_log, code_attachments(message))


def record_sent(email_log):
    """
    Marks `email_log` sent, and lets go of its attachments, see `release_attachments()`.
    """
    email_log.mark_sent()
    release_attachments(email_log)


def release_attachments(email_log):
    """
    Deletes the attachments kept with `email_log` once it is sent, unless they are kept
    after sending, see ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS``. Their content
    goes with `cleanup_email_logs()`, as other emails may still use it.
    """
    keep_content = getattr(settings, "EMAILTEMPLATES_EMAIL_LOG_CONTENT", True)
    if not keep_content or attachment_retention_days() == 0:
        email_log.kept_attachments.all().delete()


def encode_attachments(attachments):
    """
    `attachments` as JSON for the Celery task: [filename, base64 content, mimetype] lists.
    """
    encoded = []
    for filename, content, *mimetype in attachments:
        encoded.append(
            [
                filename,
                base64.b64encode(as_bytes(content)).decode("ascii"),
                *mimetype[:1],
            ]
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


def get_message(email_log, attachments=None):
    """
    The email of `email_log`: an `EmailMultiAlternatives` with the plain text as its body
    and the HTML as its alternative, which the email backend records in that entry.
    `attachments` - (filename, content[, mimetype]) tuples; by default the attachments of
    its email template and the ones kept with it.
    """
    if attachments is None:
        attachments = template_attachments(email_log) + kept_attachments(email_log)
    message = EmailMultiAlternatives(
        subject=email_log.subject,
        body=email_log.text,
        from_email=email_log.from_email or None,
        to=email_log.recipients,
        cc=email_log.cc,
        bcc=email_log.bcc,
        reply_to=email_log.reply_to,
        headers=email_log.headers,
        attachments=list(attachments),
    )
    if email_log.html:
        message.attach_alternative(email_log.html, "text/html")
    message.email_log = email_log
    message.email_template = email_log.template
    message.email_language = email_log.language
    return message


def deliver(email_log, attachments=None, fail_silently=False):
    """
    Sends the email of `email_log` now, see `get_message()`. The email backend of
    emailtemplates records the attempt and its result in the entry; with another backend
    they are recorded here. Returns the number of emails sent.
    """
    message = get_message(email_log, attachments)
    try:
        sent = message.send(fail_silently=fail_silently)
    except Exception as e:
        if not getattr(message, "email_log_recorded", False):
            count_attempt(email_log)
            email_log.mark_failed("%s: %s" % (type(e).__name__, e))
        raise
    if not getattr(message, "email_log_recorded", False):
        count_attempt(email_log)
        if sent:
            record_sent(email_log)
        else:
            email_log.mark_failed("The email was not sent.")
    return sent


def count_attempt(email_log):
    EmailLog.objects.filter(pk=email_log.pk).update(attempts=models.F("attempts") + 1)
    email_log.refresh_from_db(fields=["attempts"])


def deliver_later(email_log, attachments=None):
    """
    Sends the email of `email_log` once the current transaction is committed: by the Celery
    task of `emailtemplates.tasks` with ``EMAILTEMPLATES_CELERY = True``, otherwise right
    away. `attachments` - (filename, content[, mimetype]) tuples, never saved; by default
    the attachments of its email template and the ones kept with it.
    """
    if celery_enabled():
        from .tasks import send_email

        encoded = None if attachments is None else encode_attachments(attachments)
        transaction.on_commit(lambda: send_email.delay(email_log.pk, encoded))
    else:
        transaction.on_commit(lambda: deliver_now(email_log, attachments))


def deliver_now(email_log, attachments=None):
    """
    Sends the email of `email_log`; an error is recorded in it and logged, not raised.
    """
    try:
        deliver(email_log, attachments)
    except Exception as e:
        logger.error("Problem sending email to %s: %s", email_log.recipients, e)


def resend(email_log):
    """
    Sends a failed email again, as a new entry of the history, see `deliver_later()`: with
    the attachments of its email template and the ones kept with it, which the new entry
    keeps too. Raises ValueError when an attachment cannot be attached again, see
    `missing_attachments()`, rather than sending the email without it.
    """
    email_log = EmailLog.objects.get(pk=email_log.pk)
    missing = missing_attachments(email_log)
    if missing:
        raise ValueError(
            "The attachments %s of the email cannot be attached again."
            % ", ".join(missing)
        )
    kept = list(email_log.kept_attachments.all())
    template_names = [
        os.path.basename(attachment.attachment_file.name)
        for attachment in template_kept_attachments(email_log)
    ]
    with transaction.atomic():
        email_log.pk = None
        email_log.status = EmailLog.PENDING
        email_log.attempts = 0
        email_log.last_error = ""
        email_log.sent_at = None
        email_log.source = email_log.source_id = ""
        email_log.source_seq = 0
        email_log.source_context = {}
        email_log.created = now()
        email_log.attachments = template_names + [
            attachment.name for attachment in kept
        ]
        email_log.save()
        # the content is shared, not copied
        EmailLogAttachment.objects.bulk_create(
            EmailLogAttachment(
                email_log=email_log,
                name=attachment.name,
                mimetype=attachment.mimetype,
                content_id=attachment.content_id,
            )
            for attachment in kept
        )
        deliver_later(email_log)
    return email_log


def cleanup_email_logs(retention_days=None):
    """
    Deletes the sent emails older than ``EMAILTEMPLATES_EMAIL_LOG_RETENTION_DAYS`` (or
    `retention_days`), the attachments of sent emails older than
    ``EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS``, and the content of attachments
    no email uses any more; pending and failed emails keep their attachments, until someone
    acts on them. Returns the numbers of emails and of attachment contents deleted.
    """
    with transaction.atomic():
        _total, deleted = EmailLog.objects.past_retention(retention_days).delete()
        emails = deleted.get(EmailLog._meta.label, 0)
        attachment_days = attachment_retention_days()
        if attachment_days is not None:
            EmailLogAttachment.objects.filter(
                email_log__status=EmailLog.SENT,
                email_log__sent_at__lt=now() - timedelta(days=attachment_days),
            ).delete()
        # only the ids are loaded, not the content
        _total, deleted = (
            EmailLogAttachmentContent.objects.filter(attachments__isnull=True)
            .only("pk")
            .delete()
        )
        contents = deleted.get(EmailLogAttachmentContent._meta.label, 0)
    return emails, contents
