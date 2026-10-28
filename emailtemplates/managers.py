# coding=utf-8
"""
The manager of `emailtemplates.models.EmailLog`, and what it records: `EmailContent`, the
email, and `EmailSource`, what sent it.
"""

from dataclasses import asdict, dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.timezone import now


@dataclass(frozen=True)
class EmailSource:
    """
    What sent an email, as the `source*` fields of `EmailLog`: for a Celery task its name,
    its id, the position of the email among the emails of the run and the arguments of the
    task, see `emailtemplates.backends`. Empty for an email sent outside of a task.
    """

    source: str = ""
    source_id: str = ""
    source_seq: int = 0
    source_context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EmailContent:
    """
    One email as `EmailLog` keeps it.
    """

    recipients: list = field(default_factory=list)
    template: str = ""
    language: str = ""
    subject: str = ""
    from_email: str = ""
    cc: list = field(default_factory=list)
    bcc: list = field(default_factory=list)
    reply_to: list = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    html: str = ""
    text: str = ""
    # the file names
    attachments: list = field(default_factory=list)

    @classmethod
    def from_message(cls, message):
        """
        The email of `message`, an `EmailMessage`. The template comes from
        `EmailFromTemplate`, which marks its messages, see `get_message_object()`; the HTML
        is the alternative of an `EmailMultiAlternatives`, or the body of a message sent as
        HTML.
        """
        alternatives = getattr(message, "alternatives", [])
        html = next(
            (content for content, mimetype in alternatives if mimetype == "text/html"),
            "",
        )
        text = message.body
        if not html and getattr(message, "content_subtype", "") == "html":
            html, text = message.body, ""
        return cls(
            recipients=list(message.to),
            template=getattr(message, "email_template", ""),
            language=getattr(message, "email_language", ""),
            subject=str(message.subject or "")[:998],
            from_email=message.from_email or "",
            cc=list(message.cc),
            bcc=list(message.bcc),
            reply_to=list(message.reply_to),
            headers=dict(message.extra_headers),
            html=html,
            text=text,
            attachments=[
                (
                    attachment[0]
                    if isinstance(attachment, tuple)
                    else attachment.get_filename()
                )
                for attachment in message.attachments
            ],
        )


class EmailLogQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=self.model.PENDING)

    def failed(self):
        return self.filter(status=self.model.FAILED)

    def unsent(self):
        return self.exclude(status=self.model.SENT)

    def sent(self):
        return self.filter(status=self.model.SENT)

    def past_retention(self, retention_days=None):
        """
        Sent emails old enough to be deleted, see `cleanup_email_logs`. Pending and failed
        ones are kept whatever their age: an email that did not go out stays visible, and
        can be sent again from the admin, until someone acts on it.
        """
        if retention_days is None:
            retention_days = getattr(
                settings, "EMAILTEMPLATES_EMAIL_LOG_RETENTION_DAYS", 180
            )
        return self.sent().filter(created__lt=now() - timedelta(days=retention_days))

    def for_source(self, source_id):
        """
        The emails of one run of a source (e.g. one Celery task id), in the order sent.
        """
        return self.filter(source_id=source_id).order_by("source_seq")


class EmailLogManager(models.Manager):
    def record_attempt(self, content, source=EmailSource()):
        """
        Creates - or, when the run that sends it is run again (a Celery retry), reuses - the
        entry of the email `content` (`EmailContent`) sent by `source` (`EmailSource`) and
        counts the attempt. Called by the email backend right before the email is handed to
        the real backend, so the entry exists even if sending hangs or the worker is killed,
        see `emailtemplates.backends`.

        A run is identified by `source.source_id` (e.g. the Celery task id) and the email
        within it by `source.source_seq`, its position among the emails the run sends: one
        run may send several emails, which must not collapse onto one entry. The recipients
        and the content are not part of the key, as they may differ between attempts (e.g.
        the ``date`` of the context). An entry already sent is never reused: an email sent
        again by a redelivered task gets an entry of its own.
        """
        fields = dict(asdict(content), **asdict(source))
        if source.source_id:
            email_log = (
                self.filter(source_id=source.source_id, source_seq=source.source_seq)
                .exclude(status=self.model.SENT)
                .order_by("-created")
                .first()
            )
            if email_log is not None:
                for name, value in fields.items():
                    setattr(email_log, name, value)
                email_log.status = self.model.PENDING
                email_log.attempts = models.F("attempts") + 1
                email_log.save(
                    update_fields=[*fields, "status", "attempts", "modified"]
                )
                email_log.refresh_from_db()
                return email_log
        return self.create(status=self.model.PENDING, attempts=1, **fields)
