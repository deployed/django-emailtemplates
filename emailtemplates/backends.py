# coding=utf-8
"""
Email backends keeping the history of sent emails (`emailtemplates.models.EmailLog`).

Every email sent through them is recorded as pending before it is handed to the real
backend, so the entry exists even if sending hangs or the worker is killed, and marked
sent or failed afterwards::

    EMAIL_BACKEND = "emailtemplates.backends.EmailBackend"
    EMAILTEMPLATES_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

`EmailBackend` hands the emails to ``EMAILTEMPLATES_EMAIL_BACKEND`` (SMTP by default), so
a backend of the project (e.g. one adding a Bcc) keeps working behind it; a backend may
also mix `EmailLogBackendMixin` in itself.

Inside a Celery task the entries describe the task (name, id, arguments) and a retry of
the task updates the entries of its run instead of adding new ones; with `EmailTask` as
the base of the task, the entries are marked failed once the retries run out.
"""

from dataclasses import asdict

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend
from django.db import models

from .managers import EmailContent, EmailSource
from .utils import suppress_and_log

try:
    from celery import current_task
except ImportError:  # optional, see emailtemplates.tasks
    current_task = None

# The attribute of the request of a Celery task counting the emails one run of the task has
# handed to the backend so far: the request is new for every run, including every retry.
EMAIL_LOG_SEQ_REQUEST_ATTR = "_emailtemplates_email_log_seq"


def task_context(args, kwargs):
    """
    What a Celery task was called with, as `EmailLog.source_context`.
    """
    return {"args": list(args or []), "kwargs": dict(kwargs or {})}


def get_current_task():
    """
    The Celery task running the code, if it was dispatched (by a worker, or by
    ``Task.apply()``), so that its retries and failures go through `EmailTask`. A task
    called directly, e.g. in a test, is not one.
    """
    task = current_task
    if task and not task.request.called_directly:
        return task
    return None


class EmailLogBackendMixin:
    """
    Records the emails sent by the backend it is mixed into in `EmailLog`, see the module.
    """

    def send_messages(self, messages):
        if not messages:
            return 0
        email_logs = self.record_pending(messages)
        return sum(
            self.send_one(message, email_log)
            for message, email_log in zip(messages, email_logs)
        )

    def send_one(self, message, email_log):
        """
        Sends one email and records the result. One by one, so that an error in the middle
        of a batch does not mark the emails sent before it as failed.
        """
        try:
            sent = self.send_to_backend(message)
        except Exception as e:
            self.record_failure(email_log, e)
            raise
        if sent:
            self.record_sent(email_log)
        else:
            self.record_failure(
                email_log,
                "The email was not sent (fail_silently suppressed the error).",
            )
        return sent

    def send_to_backend(self, message):
        return super(EmailLogBackendMixin, self).send_messages([message])

    @staticmethod
    def next_source_seqs(task, count):
        """
        `count` consecutive positions, not used yet by this run of `task`, e.g. 0 and 1 for
        its first two emails, then 2 for a third one sent later. Counted on the request of
        the task, which lives for one run: every email sent opens a backend of its own, and
        a retry starts from 0 again, so that it maps onto the entries of the first run.
        """
        start = getattr(task.request, EMAIL_LOG_SEQ_REQUEST_ATTR, 0)
        setattr(task.request, EMAIL_LOG_SEQ_REQUEST_ATTR, start + count)
        return range(start, start + count)

    @classmethod
    def get_email_sources(cls, count):
        """
        What sent the `count` emails about to be sent, one `EmailSource` each: inside a
        Celery task the task, with the position of every email in its run.
        """
        task = get_current_task()
        if task is None:
            return [EmailSource() for _ in range(count)]
        context = task_context(task.request.args, task.request.kwargs)
        return [
            EmailSource(
                source=task.name,
                source_id=task.request.id or "",
                source_seq=seq,
                source_context=context,
            )
            for seq in cls.next_source_seqs(task, count)
        ]

    @classmethod
    def record_pending(cls, messages):
        """
        A pending entry for every message, in the same order; None for a message whose
        entry could not be written (logged, not raised). A message of
        `EmailLog.get_message()` brings its entry, see `EmailFromTemplate.send_later()`.
        """
        from .models import EmailLog

        email_logs = []
        for message, source in zip(messages, cls.get_email_sources(len(messages))):
            email_log = None
            with suppress_and_log(
                message="Could not record the email to %s" % (message.to,)
            ):
                email_log = getattr(message, "email_log", None)
                if email_log is not None:
                    EmailLog.objects.filter(pk=email_log.pk).update(
                        status=EmailLog.PENDING,
                        attempts=models.F("attempts") + 1,
                        **asdict(source),
                    )
                    email_log.refresh_from_db()
                else:
                    email_log = EmailLog.objects.record_attempt(
                        EmailContent.from_message(message), source
                    )
                message.email_log_recorded = True
            email_logs.append(email_log)
        return email_logs

    @staticmethod
    def record_sent(email_log):
        if email_log is None:
            return
        with suppress_and_log(
            message="Could not mark email log %s sent" % email_log.pk
        ):
            email_log.mark_sent()

    @staticmethod
    def record_failure(email_log, error):
        """
        Inside a task based on `EmailTask` only the error is recorded: the task may be
        retried, and `EmailTask` marks the email failed once the retries run out. Anywhere
        else the email failed for good.
        """
        if email_log is None:
            return
        task = get_current_task()
        with suppress_and_log(
            message="Could not record the error of %s" % email_log.pk
        ):
            if getattr(task, "records_email_failures", False):
                email_log.last_error = str(error)
                email_log.save(update_fields=["last_error", "modified"])
            else:
                email_log.mark_failed(error)


class EmailBackend(EmailLogBackendMixin, BaseEmailBackend):
    """
    Records the emails and hands them to ``EMAILTEMPLATES_EMAIL_BACKEND`` (SMTP by default).
    """

    def __init__(self, fail_silently=False, **kwargs):
        super(EmailBackend, self).__init__(fail_silently=fail_silently)
        self.connection = get_connection(
            getattr(
                settings,
                "EMAILTEMPLATES_EMAIL_BACKEND",
                "django.core.mail.backends.smtp.EmailBackend",
            ),
            fail_silently=fail_silently,
            **kwargs,
        )

    def open(self):
        return self.connection.open()

    def close(self):
        return self.connection.close()

    def send_to_backend(self, message):
        return self.connection.send_messages([message])
