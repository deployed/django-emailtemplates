# coding=utf-8
"""
Celery (an optional dependency: ``pip install django-emailtemplates[celery]``) for sending
emails and keeping their history, see `emailtemplates.backends`.

* `EmailTask` - the base of tasks sending emails, recording their retries and failures.
* `send_email` - sends an email of `EmailFromTemplate.send_later()` with
  ``EMAILTEMPLATES_CELERY = True``, retrying a failed sending with a growing delay,
  ``EMAILTEMPLATES_CELERY_MAX_RETRIES`` times (3 by default), on the queue
  ``EMAILTEMPLATES_CELERY_QUEUE`` (the default one by default).
* `cleanup_email_logs` - deletes old sent emails, e.g. run daily by Celery beat.
"""

import logging
from smtplib import SMTPException

from celery import Task, shared_task
from django.conf import settings

from .backends import task_context
from .email import decode_attachments
from .models import EmailLog

logger = logging.getLogger(__name__)


class EmailTask(Task):
    """
    Records the error of a retry, and the failure once the retries run out, in the
    entries (`EmailLog`) of the emails the run of the task sent, see
    `emailtemplates.backends`.
    """

    # the email backend leaves marking the emails failed to on_failure(), see
    # EmailLogBackendMixin.record_failure()
    records_email_failures = True

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.debug("Retrying email task %s: %s", task_id, exc)
        self.record_error(task_id, exc, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("Email task %s failed", task_id, exc_info=einfo.exc_info)
        self.record_error(task_id, exc, args, kwargs, failed=True)

    def record_error(self, task_id, exc, args, kwargs, failed=False):
        """
        The emails of the run already sent are left alone: a run that failed on its second
        email must not report the first one, which went out, as failed. A run that failed
        before sending anything (e.g. rendering failed) gets an entry for the failure, with
        the arguments of the task. A problem recording it never hides the original error.
        """
        try:
            email_logs = list(EmailLog.objects.for_source(task_id))
            if not email_logs and failed:
                email_logs = [
                    EmailLog.objects.create(
                        source=self.name,
                        source_id=task_id,
                        source_context=task_context(args, kwargs),
                    )
                ]
            for email_log in email_logs:
                if email_log.status == EmailLog.SENT:
                    continue
                if failed:
                    email_log.mark_failed(exc)
                else:
                    email_log.last_error = str(exc)
                    email_log.save(update_fields=["last_error", "modified"])
        except Exception:
            logger.exception("Could not record the error of email task %s", task_id)


_send_email_options = {}
if getattr(settings, "EMAILTEMPLATES_CELERY_QUEUE", None):
    _send_email_options["queue"] = settings.EMAILTEMPLATES_CELERY_QUEUE


@shared_task(
    base=EmailTask,
    autoretry_for=(SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=getattr(settings, "EMAILTEMPLATES_CELERY_MAX_RETRIES", 3),
    **_send_email_options
)
def send_email(email_log_id, attachments=()):
    """
    Sends the email of the `EmailLog` of `email_log_id`, unless it is gone or sent already.
    `attachments` - see `emailtemplates.email.encode_attachments()`.
    """
    email_log = EmailLog.objects.filter(pk=email_log_id).first()
    if email_log is None or email_log.status == EmailLog.SENT:
        return 0
    return email_log.deliver(decode_attachments(attachments))


@shared_task
def cleanup_email_logs(retention_days=None):
    """
    Deletes the sent emails older than ``EMAILTEMPLATES_EMAIL_LOG_RETENTION_DAYS`` (180 by
    default); pending and failed ones are kept, see `EmailLogQuerySet.past_retention()`.
    """
    deleted, _ = EmailLog.objects.past_retention(retention_days).delete()
    if deleted:
        logger.info("Deleted %s sent email logs", deleted)
    return deleted
