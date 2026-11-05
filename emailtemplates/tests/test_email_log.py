# coding=utf-8
import os
from datetime import timedelta
from io import StringIO
from smtplib import SMTPException

import mock
from celery import shared_task
from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.core.mail.backends.locmem import EmailBackend as LocMemEmailBackend
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from email.mime.image import MIMEImage

from ..backends import EmailLogBackendMixin
from ..checks import check_celery, check_email_backend
from ..email import EmailFromTemplate
from ..history import (
    cleanup_email_logs as cleanup_email_logs_now,
    decode_attachments,
    encode_attachments,
    MissingAttachments,
    kept_attachments,
    missing_attachments,
    resend,
)
from ..managers import EmailContent, EmailSource
from ..models import (
    EmailAttachment,
    EmailLog,
    EmailLogAttachment,
    EmailLogAttachmentContent,
    EmailTemplate,
    MassEmailAttachment,
    MassEmailMessage,
    now,
)
from ..tasks import EmailTask, cleanup_email_logs, send_email

TITLE = "email_log.html"
LANGUAGE = "pl"
TO = ["anna@example.com"]
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
SEND = "django.core.mail.backends.locmem.EmailBackend.send_messages"


class LoggingLocMemBackend(EmailLogBackendMixin, LocMemEmailBackend):
    """A backend of a project with the history mixed in."""


@shared_task(base=EmailTask, autoretry_for=(SMTPException,), max_retries=1)
def send_two_emails(name):
    send_mail("First", "Hello %s" % name, None, ["first@example.com"])
    send_mail("Second", "Hello %s" % name, None, ["second@example.com"])


@shared_task(base=EmailTask, autoretry_for=(SMTPException,), max_retries=1)
def send_invoice():
    message = mail.EmailMessage("Invoice", "Attached", None, ["first@example.com"])
    message.attach("invoice.pdf", b"%PDF-1.4", "application/pdf")
    message.send()


@shared_task(base=EmailTask)
def fail_before_sending(name):
    raise ValueError("Cannot render")


@shared_task
def send_without_email_task(name):
    send_mail("Plain task", "Hello %s" % name, None, ["first@example.com"])


@override_settings(
    EMAIL_BACKEND="emailtemplates.backends.EmailBackend",
    EMAILTEMPLATES_EMAIL_BACKEND=LOCMEM,
)
class EmailLogTestCase(TestCase):
    def setUp(self):
        self.email_template = EmailTemplate.objects.create(
            title=TITLE,
            language=LANGUAGE,
            subject="Hello {{ name }}",
            content="<p>Hello {{ name }}</p>",
        )

    def get_eft(self):
        eft = EmailFromTemplate(
            name=TITLE, language=LANGUAGE, registry_validation=False
        )
        eft.context = {"name": "Anna"}
        return eft

    def add_template_attachment(self):
        attachment = EmailAttachment(name="Terms", send_as_link=False)
        attachment.attachment_file.save("terms.txt", ContentFile(b"The terms"))
        self.email_template.attachments.add(attachment)
        return os.path.basename(attachment.attachment_file.name)  # e.g. terms_ab12.txt


class BackendTest(EmailLogTestCase):
    def test_email_of_a_template_is_recorded(self):
        self.assertEqual(self.get_eft().send(TO, cc=["boss@example.com"]), 1)
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.status, EmailLog.SENT)
        self.assertEqual((email_log.template, email_log.language), (TITLE, LANGUAGE))
        self.assertEqual(email_log.recipients, TO)
        self.assertEqual(email_log.cc, ["boss@example.com"])
        self.assertEqual(email_log.subject, "Hello Anna")
        self.assertEqual(email_log.html, "<p>Hello Anna</p>")
        self.assertEqual(email_log.text, "Hello Anna")
        self.assertEqual(email_log.attempts, 1)
        self.assertIsNotNone(email_log.sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_every_email_is_recorded(self):
        send_mail("Plain", "Text only", "shop@example.com", TO)
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.status, EmailLog.SENT)
        self.assertEqual((email_log.template, email_log.text), ("", "Text only"))
        self.assertEqual(email_log.source, "")

    def test_attachments_are_recorded_by_name(self):
        terms = self.add_template_attachment()
        self.get_eft().send(
            TO, attachments=[("invoice.pdf", b"%PDF", "application/pdf")]
        )
        self.assertEqual(EmailLog.objects.get().attachments, [terms, "invoice.pdf"])

    def test_failure_is_recorded_and_raised(self):
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            with self.assertRaises(SMTPException):
                send_mail("Plain", "Text", None, TO)
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.status, EmailLog.FAILED)
        self.assertEqual(email_log.last_error, "refused")

    def test_a_failure_does_not_fail_the_emails_sent_before_it(self):
        messages = [
            mail.EmailMessage("One", "1", None, ["one@example.com"]),
            mail.EmailMessage("Two", "2", None, ["two@example.com"]),
        ]
        with mock.patch(SEND, side_effect=[1, SMTPException("busy")]):
            with self.assertRaises(SMTPException):
                mail.get_connection().send_messages(messages)
        self.assertEqual(
            dict(EmailLog.objects.values_list("subject", "status")),
            {"One": EmailLog.SENT, "Two": EmailLog.FAILED},
        )

    def test_suppressed_failure_is_recorded(self):
        with mock.patch(SEND, return_value=0):
            send_mail("Plain", "Text", None, TO, fail_silently=True)
        self.assertEqual(EmailLog.objects.get().status, EmailLog.FAILED)

    @override_settings(
        EMAIL_BACKEND="emailtemplates.tests.test_email_log.LoggingLocMemBackend"
    )
    def test_mixed_into_a_backend_of_the_project(self):
        send_mail("Plain", "Text", None, TO)
        self.assertEqual(EmailLog.objects.get().status, EmailLog.SENT)
        self.assertEqual(len(mail.outbox), 1)

    def test_history_never_stops_an_email(self):
        with mock.patch(
            "emailtemplates.managers.EmailLogManager.record_attempt",
            side_effect=Exception("database down"),
        ):
            send_mail("Plain", "Text", None, TO)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_CONTENT=False)
    def test_content_is_not_kept_when_turned_off(self):
        self.get_eft().send(TO)
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.subject, "Hello Anna")
        self.assertEqual((email_log.html, email_log.text), ("", ""))


class RecordAttemptTest(TestCase):
    """
    The key of `EmailLog.objects.record_attempt()`: the run of a source and the position of
    the email in it, without Celery.
    """

    def record(self, source_id="", source_seq=0, **content):
        content = EmailContent(**{"recipients": TO, "subject": "Subject", **content})
        return EmailLog.objects.record_attempt(
            content, EmailSource(source_id=source_id, source_seq=source_seq)
        )

    def test_without_a_source_id_every_call_creates_an_entry(self):
        self.record()
        self.record()
        self.assertEqual(EmailLog.objects.count(), 2)

    def test_the_same_run_and_position_reuses_the_entry(self):
        first = self.record("run-1", 0)
        second = self.record("run-1", 0, subject="Second subject")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual((second.attempts, second.subject), (2, "Second subject"))

    def test_another_position_in_the_run_is_another_email(self):
        first = self.record("run-2", 0)
        second = self.record("run-2", 1)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual((first.attempts, second.attempts), (1, 1))

    def test_a_sent_entry_is_never_reused(self):
        first = self.record("run-3", 0)
        first.mark_sent()
        second = self.record("run-3", 0, subject="Redelivered")
        self.assertNotEqual(first.pk, second.pk)
        first.refresh_from_db()
        self.assertEqual(first.status, EmailLog.SENT)

    def test_content_defaults_to_empty_lists(self):
        email_log = EmailLog.objects.record_attempt(EmailContent(recipients=TO))
        self.assertEqual(
            (email_log.cc, email_log.bcc, email_log.attachments), ([], [], [])
        )
        self.assertEqual(email_log.source_context, {})

    def test_content_of_a_message_sent_as_html(self):
        message = mail.EmailMessage("Hi", "<p>Hi</p>", None, TO)
        message.content_subtype = "html"
        content = EmailContent.from_message(message)
        self.assertEqual((content.html, content.text), ("<p>Hi</p>", ""))


class CeleryTaskTest(EmailLogTestCase):
    def test_emails_of_a_task_describe_it(self):
        send_two_emails.apply(args=["Anna"], task_id="task-1")
        first, second = EmailLog.objects.for_source("task-1")
        self.assertEqual((first.subject, first.source_seq), ("First", 0))
        self.assertEqual((second.subject, second.source_seq), ("Second", 1))
        self.assertEqual(first.source, send_two_emails.name)
        self.assertEqual(first.source_context, {"args": ["Anna"], "kwargs": {}})

    def test_a_retry_updates_the_entries_of_the_run(self):
        sends = [1, SMTPException("busy"), 1, 1]
        with mock.patch(SEND, side_effect=sends):
            send_two_emails.apply(args=["Anna"], task_id="task-1")
        self.assertEqual(
            [
                (email_log.subject, email_log.status, email_log.attempts)
                for email_log in EmailLog.objects.order_by("created", "pk")
            ],
            [
                ("First", EmailLog.SENT, 1),
                ("Second", EmailLog.SENT, 2),
                # the first email went out in the first run already, sent again by the retry
                ("First", EmailLog.SENT, 1),
            ],
        )

    def test_failed_once_the_retries_run_out(self):
        with mock.patch(
            SEND, side_effect=[1, SMTPException("busy"), 1, SMTPException("busy")]
        ):
            send_two_emails.apply(args=["Anna"], task_id="task-1")
        second = EmailLog.objects.get(subject="Second")
        self.assertEqual(second.status, EmailLog.FAILED)
        self.assertEqual((second.attempts, second.last_error), (2, "busy"))
        self.assertFalse(EmailLog.objects.filter(subject="First").failed().exists())

    def test_failure_in_a_task_without_email_task_is_final(self):
        # no EmailTask.on_failure() to mark it failed later, so it is never left pending
        with mock.patch(SEND, side_effect=SMTPException("busy")):
            send_without_email_task.apply(args=["Anna"], task_id="task-5")
        email_log = EmailLog.objects.get()
        self.assertEqual(
            (email_log.status, email_log.source_id), (EmailLog.FAILED, "task-5")
        )

    def test_failure_before_sending_is_recorded(self):
        fail_before_sending.apply(args=["Anna"], task_id="task-2")
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.status, EmailLog.FAILED)
        self.assertEqual(email_log.last_error, "Cannot render")
        self.assertEqual(email_log.source_context, {"args": ["Anna"], "kwargs": {}})


class SendLaterTest(EmailLogTestCase):
    def test_sent_after_the_transaction_is_committed(self):
        with self.captureOnCommitCallbacks() as callbacks:
            email_log = self.get_eft().send_later(TO)
            self.assertEqual(email_log.status, EmailLog.PENDING)
            self.assertEqual(mail.outbox, [])
        for callback in callbacks:
            callback()
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.SENT)
        self.assertEqual(email_log.attempts, 1)
        self.assertEqual(EmailLog.objects.count(), 1)
        self.assertEqual(mail.outbox[0].subject, "Hello Anna")

    def test_attachments_are_sent(self):
        terms = self.add_template_attachment()
        with self.captureOnCommitCallbacks(execute=True):
            self.get_eft().send_later(TO, attachments=[("a.txt", "Text", "text/plain")])
        self.assertEqual(
            [attachment[0] for attachment in mail.outbox[0].attachments],
            [terms, "a.txt"],
        )

    def test_failure_is_recorded_not_raised(self):
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            with self.captureOnCommitCallbacks(execute=True):
                email_log = self.get_eft().send_later(TO)
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.FAILED)

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_recorded_with_any_backend(self):
        with self.captureOnCommitCallbacks(execute=True):
            email_log = self.get_eft().send_later(TO)
        email_log.refresh_from_db()
        self.assertEqual((email_log.status, email_log.attempts), (EmailLog.SENT, 1))

    @override_settings(EMAILTEMPLATES_CELERY=True)
    def test_with_celery_the_task_sends_it(self):
        with mock.patch("emailtemplates.tasks.send_email.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                email_log = self.get_eft().send_later(
                    TO, attachments=[("a.pdf", b"%PDF", "application/pdf")]
                )
        # the attachment is kept with the entry, so only the entry goes through the broker
        delay.assert_called_once_with(email_log.pk, None)
        self.assertEqual(mail.outbox, [])

        send_email.apply(args=delay.call_args.args, task_id="task-3")
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.SENT)
        self.assertEqual(email_log.source_id, "task-3")
        self.assertEqual(EmailLog.objects.count(), 1)
        self.assertEqual(
            mail.outbox[0].attachments, [("a.pdf", b"%PDF", "application/pdf")]
        )

    @override_settings(
        EMAILTEMPLATES_CELERY=True, EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS=False
    )
    def test_without_kept_attachments_the_task_gets_them(self):
        with mock.patch("emailtemplates.tasks.send_email.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                email_log = self.get_eft().send_later(
                    TO, attachments=[("a.pdf", b"%PDF", "application/pdf")]
                )
        delay.assert_called_once_with(
            email_log.pk, encode_attachments([("a.pdf", b"%PDF", "application/pdf")])
        )
        self.assertFalse(email_log.kept_attachments.exists())

        send_email.apply(args=delay.call_args.args)
        self.assertEqual(
            mail.outbox[0].attachments, [("a.pdf", b"%PDF", "application/pdf")]
        )

    def test_the_task_retries_and_fails_once_the_retries_run_out(self):
        with mock.patch("emailtemplates.history.transaction.on_commit"):
            email_log = self.get_eft().send_later(TO)
        with mock.patch(SEND, side_effect=SMTPException("busy")):
            send_email.apply(args=[email_log.pk], task_id="task-4")
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.FAILED)
        self.assertEqual(email_log.attempts, send_email.max_retries + 1)
        self.assertEqual(EmailLog.objects.count(), 1)

    def test_sent_emails_are_not_sent_again_by_the_task(self):
        self.get_eft().send(TO)
        self.assertEqual(send_email.run(EmailLog.objects.get().pk), 0)
        self.assertEqual(send_email.run(0), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_attachments_survive_the_json_of_the_task(self):
        attachments = [("a.txt", "Zażółć", "text/plain"), ("b.bin", b"\x00\x01")]
        self.assertEqual(
            decode_attachments(encode_attachments(attachments)),
            [("a.txt", "Zażółć".encode("utf-8"), "text/plain"), ("b.bin", b"\x00\x01")],
        )


class ResendTest(EmailLogTestCase):
    def test_a_new_entry_with_the_attachments_of_the_template(self):
        terms = self.add_template_attachment()
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO)
        failed = EmailLog.objects.get()
        self.assertTrue(failed.can_resend())

        with self.captureOnCommitCallbacks(execute=True):
            again = resend(failed)
        again.refresh_from_db()
        self.assertNotEqual(again.pk, failed.pk)
        self.assertEqual((again.status, again.attempts), (EmailLog.SENT, 1))
        self.assertEqual(again.attachments, [terms])
        self.assertEqual(mail.outbox[0].attachments[0][0], terms)
        failed.refresh_from_db()
        self.assertEqual(failed.status, EmailLog.FAILED)

    def test_only_failed_emails_can_be_sent_again(self):
        self.assertFalse(EmailLog(status=EmailLog.PENDING).can_resend())
        self.assertFalse(EmailLog(status=EmailLog.SENT).can_resend())


class EmailLogAdminTest(EmailLogTestCase):
    url = "/admin/emailtemplates/emaillog/"

    def setUp(self):
        super(EmailLogAdminTest, self).setUp()
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO)
        self.failed = EmailLog.objects.get()
        self.client.force_login(
            User.objects.create_superuser("admin", "admin@example.com", "x")
        )

    def test_history_with_the_html_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "anna@example.com")
        self.assertContains(response, "emailtemplates-status--failed")
        # a button of the form of the change list, which a form cannot be nested in
        self.assertContains(
            response, 'formaction="%s%s/resend/"' % (self.url, self.failed.pk)
        )
        self.assertNotContains(response, '<form method="post" action="%s' % self.url)
        response = self.client.get("%s%s/change/" % (self.url, self.failed.pk))
        self.assertContains(response, 'srcdoc="&lt;p&gt;Hello Anna&lt;/p&gt;"')
        self.assertNotContains(response, 'name="_save"')

    def test_search_by_recipient(self):
        send_mail("Other", "Text", None, ["jan@example.com"])
        response = self.client.get(self.url, {"q": "jan@"})
        self.assertContains(response, "jan@example.com")
        self.assertNotContains(response, "anna@example.com")

    def test_no_adding(self):
        self.assertEqual(self.client.get(self.url + "add/").status_code, 403)

    def test_send_now(self):
        url = "%s%s/resend/" % (self.url, self.failed.pk)
        self.assertEqual(self.client.get(url).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        self.assertEqual(EmailLog.objects.sent().count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_send_selected_skips_emails_not_failed(self):
        send_mail("Plain", "Text", None, TO)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                {
                    "action": "resend_selected",
                    "_selected_action": list(
                        EmailLog.objects.values_list("pk", flat=True)
                    ),
                },
                follow=True,
            )
        self.assertContains(response, "1 email is being sent again.")
        self.assertContains(response, "1 email was skipped")
        self.assertEqual(EmailLog.objects.count(), 3)

    def test_staff_viewing_the_history_cannot_send_again(self):
        staff = User.objects.create_user(
            "staff", "staff@example.com", "x", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_emaillog"))
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/resend/")
        self.assertNotContains(response, "resend_selected")
        url = "%s%s/resend/" % (self.url, self.failed.pk)
        self.assertEqual(self.client.post(url).status_code, 403)


class CleanupTest(EmailLogTestCase):
    def test_old_sent_emails_are_deleted_failed_ones_kept(self):
        old = now() - timedelta(days=181)
        send_mail("Old", "Text", None, TO)
        send_mail("New", "Text", None, TO)
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            with self.assertRaises(SMTPException):
                send_mail("Old failed", "Text", None, TO)
        EmailLog.objects.filter(subject__startswith="Old").update(created=old)

        out = StringIO()
        call_command("cleanup_email_logs", stdout=out)
        self.assertIn("Deleted 1", out.getvalue())
        self.assertEqual(
            sorted(EmailLog.objects.values_list("subject", flat=True)),
            ["New", "Old failed"],
        )
        self.assertEqual(cleanup_email_logs(retention_days=0), 1)

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_RETENTION_DAYS=30)
    def test_retention_from_the_settings(self):
        send_mail("Month old", "Text", None, TO)
        EmailLog.objects.update(created=now() - timedelta(days=31))
        self.assertEqual(cleanup_email_logs(), 1)


class CeleryCheckTest(TestCase):
    @override_settings(EMAILTEMPLATES_CELERY=True)
    def test_error_without_celery(self):
        self.assertEqual(check_celery(None), [])
        with mock.patch("emailtemplates.checks.find_spec", return_value=None):
            errors = check_celery(None)
        self.assertEqual([error.id for error in errors], ["emailtemplates.E002"])


class FailedInvoiceMixin:
    PDF = ("invoice.pdf", b"%PDF-1.4", "application/pdf")

    def fail_sending(self):
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO, attachments=[self.PDF])
        return EmailLog.objects.get()


class KeptAttachmentsTest(FailedInvoiceMixin, EmailLogTestCase):
    """
    The attachments of an email - of its email template and the ones added by code - are
    kept with it, in the database, so that it is sent, later or again, with them.
    """

    def test_all_attachments_are_kept(self):
        terms = self.add_template_attachment()
        self.get_eft().send(TO, attachments=[self.PDF])
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.attachments, [terms, "invoice.pdf"])
        attachment = email_log.kept_attachments.get(name="invoice.pdf")
        self.assertEqual(attachment.mimetype, "application/pdf")
        self.assertEqual(attachment.content.size, len(self.PDF[1]))
        self.assertEqual(
            kept_attachments(email_log),
            [(terms, b"The terms", "text/plain"), self.PDF],
        )

    def test_a_file_of_the_code_named_like_one_of_the_template_is_kept(self):
        terms = self.add_template_attachment()
        mine = (terms, b"My own terms", "text/plain")
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO, attachments=[mine])
        failed = EmailLog.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            resend(failed)
        self.assertEqual(
            sorted(content for _name, content, _type in mail.outbox[0].attachments),
            ["My own terms", "The terms"],
        )

    def test_send_later_keeps_them_and_sends_them(self):
        terms = self.add_template_attachment()
        with self.captureOnCommitCallbacks(execute=True):
            email_log = self.get_eft().send_later(TO, attachments=[self.PDF])
        self.assertEqual(
            sorted(email_log.kept_attachments.values_list("name", flat=True)),
            sorted([terms, "invoice.pdf"]),
        )
        self.assertEqual(
            [attachment[0] for attachment in mail.outbox[0].attachments],
            [terms, "invoice.pdf"],
        )

    def test_send_later_sends_what_it_recorded(self):
        # the template changes before the email is sent in the background
        terms = self.add_template_attachment()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.get_eft().send_later(TO)
        self.email_template.attachments.all().delete()
        for callback in callbacks:
            callback()
        self.assertEqual(
            mail.outbox[0].attachments, [(terms, "The terms", "text/plain")]
        )

    def test_a_template_of_another_language_or_object_does_not_matter(self):
        terms = self.add_template_attachment()
        failed = self.fail_sending()
        EmailLog.objects.update(language="", template="")
        failed.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            resend(failed)
        self.assertEqual(
            [attachment[0] for attachment in mail.outbox[0].attachments],
            [terms, "invoice.pdf"],
        )

    def test_a_failed_mass_email_is_sent_again_with_its_attachments(self):
        message = MassEmailMessage.objects.create(subject="News", content="<p>News</p>")
        attachment = MassEmailAttachment(mass_email_message=message, send_as_link=False)
        attachment.attachment_file.save("news.pdf", ContentFile(b"%PDF news"))
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            message.send(["anna@example.com"])
        failed = EmailLog.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            resend(failed)
        self.assertEqual(
            [attachment[0] for attachment in mail.outbox[0].attachments],
            failed.attachments,
        )

    def test_an_email_without_its_attachments_fails_rather_than_staying_pending(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            email_log = self.get_eft().send_later(TO, attachments=[self.PDF])
        email_log.kept_attachments.all().delete()
        for callback in callbacks:
            callback()
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.FAILED)
        self.assertIn("invoice.pdf", email_log.last_error)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAILTEMPLATES_CELERY=True)
    def test_the_task_marks_it_failed_without_retrying(self):
        with mock.patch("emailtemplates.history.transaction.on_commit"):
            email_log = self.get_eft().send_later(TO, attachments=[self.PDF])
        email_log.kept_attachments.all().delete()
        send_email.apply(args=[email_log.pk], task_id="task-7")
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailLog.FAILED)
        self.assertEqual(EmailLog.objects.count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_a_mime_part_without_a_name_gets_one(self):
        image = MIMEImage(b"GIF89a", "gif")
        with self.captureOnCommitCallbacks(execute=True):
            email_log = self.get_eft().send_later(TO, attachments=[image])
        self.assertEqual(email_log.attachments, ["attachment.gif"])
        self.assertEqual(
            kept_attachments(email_log), [("attachment.gif", b"GIF89a", "image/gif")]
        )
        self.assertEqual(EmailLog.objects.sent().count(), 1)

    def test_nothing_is_kept_when_the_transaction_is_rolled_back(self):
        with self.assertRaises(ZeroDivisionError):
            with transaction.atomic():
                self.get_eft().send_later(TO, attachments=[self.PDF])
                1 / 0
        self.assertFalse(EmailLog.objects.exists())
        self.assertFalse(EmailLogAttachmentContent.objects.exists())

    def test_a_failure_in_the_middle_keeps_none_of_them(self):
        second = ("second.pdf", b"%PDF-2", "application/pdf")
        create = EmailLogAttachment.objects.create

        def fail_the_second(**kwargs):
            if EmailLogAttachment.objects.exists():
                raise OSError("disk full")
            return create(**kwargs)

        with mock.patch.object(
            EmailLogAttachment.objects, "create", side_effect=fail_the_second
        ):
            with self.assertRaises(OSError):
                self.get_eft().send_later(TO, attachments=[self.PDF, second])
        self.assertFalse(EmailLog.objects.exists())
        self.assertFalse(EmailLogAttachment.objects.exists())

    def test_the_same_content_is_kept_once(self):
        # e.g. a mass email: the attachment of every recipient is the same file
        for recipient in ["anna@example.com", "jan@example.com", "ola@example.com"]:
            self.get_eft().send([recipient], attachments=[self.PDF])
        self.assertEqual(EmailLogAttachment.objects.count(), 3)
        self.assertEqual(EmailLogAttachmentContent.objects.count(), 1)

    def test_a_content_being_used_again_is_locked_against_the_cleanup(self):
        failed = self.fail_sending()
        content = failed.kept_attachments.get().content
        queries = []
        with mock.patch(
            "django.db.models.query.QuerySet.select_for_update",
            autospec=True,
            side_effect=lambda queryset, **kwargs: queries.append(kwargs) or queryset,
        ):
            self.get_eft().send(TO, attachments=[self.PDF])
            cleanup_email_logs_now()
        self.assertEqual(queries, [{}, {"skip_locked": True, "of": ("self",)}])
        self.assertTrue(
            EmailLogAttachmentContent.objects.filter(pk=content.pk).exists()
        )

    def test_a_mass_email_keeps_its_attachment_once(self):
        message = MassEmailMessage.objects.create(subject="News", content="<p>News</p>")
        attachment = MassEmailAttachment(mass_email_message=message)
        attachment.attachment_file.save("news.pdf", ContentFile(b"%PDF news"))
        message.send(["anna@example.com", "jan@example.com"])
        self.assertEqual(EmailLogAttachment.objects.count(), 2)
        self.assertEqual(EmailLogAttachmentContent.objects.count(), 1)

    def test_a_failed_email_is_sent_again_with_them(self):
        failed = self.fail_sending()
        with self.captureOnCommitCallbacks(execute=True):
            again = resend(failed)
        self.assertEqual(mail.outbox[0].attachments, [self.PDF])
        self.assertEqual(again.attachments, ["invoice.pdf"])
        # an entry of its own, sharing the content
        self.assertNotEqual(
            again.kept_attachments.get().pk, failed.kept_attachments.get().pk
        )
        self.assertEqual(EmailLogAttachmentContent.objects.count(), 1)

    def test_resending_is_all_or_nothing(self):
        failed = self.fail_sending()
        with mock.patch.object(
            EmailLogAttachment.objects, "bulk_create", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                resend(failed)
        self.assertEqual(EmailLog.objects.count(), 1)

    def test_an_email_whose_attachment_is_not_kept_is_not_sent_again(self):
        failed = self.fail_sending()
        failed.kept_attachments.all().delete()
        self.assertEqual(missing_attachments(failed), ["invoice.pdf"])
        with self.assertRaises(MissingAttachments):
            resend(failed)
        self.assertEqual(EmailLog.objects.count(), 1)

    def test_the_content_no_email_uses_goes_with_the_cleanup(self):
        failed = self.fail_sending()
        failed.delete()
        self.assertEqual(EmailLogAttachmentContent.objects.count(), 1)
        self.assertEqual(cleanup_email_logs_now(), (0, 1))
        self.assertFalse(EmailLogAttachmentContent.objects.exists())

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS=0)
    def test_retention_of_0_deletes_them_once_sent(self):
        failed = self.fail_sending()
        # still needed to send it again
        self.assertTrue(failed.kept_attachments.exists())
        self.get_eft().send(TO, attachments=[self.PDF])
        sent = EmailLog.objects.sent().get()
        self.assertFalse(sent.kept_attachments.exists())
        self.assertEqual(sent.attachments, ["invoice.pdf"])  # the name stays

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS=30)
    def test_cleanup_deletes_the_attachments_of_sent_emails_past_the_retention(self):
        failed = self.fail_sending()
        self.get_eft().send(TO, attachments=[self.PDF])
        sent = EmailLog.objects.sent().get()
        EmailLog.objects.update(sent_at=now() - timedelta(days=31))
        self.assertEqual(cleanup_email_logs(), 0)  # the emails stay
        self.assertFalse(sent.kept_attachments.exists())
        self.assertTrue(failed.kept_attachments.exists())
        # the failed email still uses the content
        self.assertEqual(EmailLogAttachmentContent.objects.count(), 1)

    def test_cleanup_of_old_emails_deletes_their_attachments(self):
        self.get_eft().send(TO, attachments=[self.PDF])
        EmailLog.objects.update(created=now() - timedelta(days=181))
        out = StringIO()
        call_command("cleanup_email_logs", stdout=out)
        self.assertIn(
            "Deleted 1 sent email logs and the content of 1 attachments",
            out.getvalue(),
        )
        self.assertFalse(EmailLogAttachmentContent.objects.exists())

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_ATTACHMENTS=False)
    def test_none_are_kept_when_turned_off(self):
        failed = self.fail_sending()
        self.assertFalse(EmailLogAttachment.objects.exists())
        self.assertEqual(missing_attachments(failed), ["invoice.pdf"])

    @override_settings(EMAILTEMPLATES_EMAIL_LOG_CONTENT=False)
    def test_no_content_kept_means_no_attachments_either(self):
        self.get_eft().send(TO, attachments=[self.PDF])
        self.assertFalse(EmailLogAttachment.objects.exists())

    def test_a_retry_of_a_task_replaces_the_attachments_of_its_run(self):
        sends = [SMTPException("busy"), 1]
        with mock.patch(SEND, side_effect=sends):
            send_invoice.apply(task_id="task-6")
        email_log = EmailLog.objects.get()
        self.assertEqual((email_log.status, email_log.attempts), (EmailLog.SENT, 2))
        self.assertEqual(email_log.kept_attachments.count(), 1)


class KeptAttachmentsAdminTest(FailedInvoiceMixin, EmailLogTestCase):
    url = "/admin/emailtemplates/emaillog/"

    def setUp(self):
        super(KeptAttachmentsAdminTest, self).setUp()
        self.client.force_login(
            User.objects.create_superuser("admin", "admin@example.com", "x")
        )

    def test_kept_attachments_are_marked(self):
        failed = self.fail_sending()
        response = self.client.get("%s%s/change/" % (self.url, failed.pk))
        self.assertContains(response, "invoice.pdf (kept)")

    def test_an_attachment_without_a_name(self):
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO, attachments=[MIMEImage(b"GIF89a", "gif")])
        failed = EmailLog.objects.get()
        failed.kept_attachments.all().delete()
        EmailLog.objects.update(attachments=[None])  # recorded without a name
        response = self.client.post("%s%s/resend/" % (self.url, failed.pk), follow=True)
        self.assertContains(response, "its attachments attachment are not kept")

    def test_a_name_kept_once_is_marked_once(self):
        terms = self.add_template_attachment()
        with mock.patch(SEND, side_effect=SMTPException("refused")):
            self.get_eft().send(TO, attachments=[(terms, b"Mine", "text/plain")])
        failed = EmailLog.objects.get()
        failed.kept_attachments.filter(content__data=b"Mine").delete()
        response = self.client.get("%s%s/change/" % (self.url, failed.pk))
        self.assertContains(response, "%s (kept)" % terms, count=1)

    def test_attachments_deleted_meanwhile_are_reported_not_an_error(self):
        failed = self.fail_sending()
        with mock.patch(
            "emailtemplates.admin.resend",
            side_effect=MissingAttachments(["invoice.pdf"]),
        ):
            response = self.client.post(
                "%s%s/resend/" % (self.url, failed.pk), follow=True
            )
        self.assertContains(response, "its attachments invoice.pdf are not kept")

    def test_an_email_without_its_attachment_is_skipped(self):
        failed = self.fail_sending()
        failed.kept_attachments.all().delete()
        response = self.client.post("%s%s/resend/" % (self.url, failed.pk), follow=True)
        self.assertContains(response, "its attachments invoice.pdf are not kept")
        self.assertEqual(EmailLog.objects.count(), 1)


class EmailBackendCheckTest(TestCase):
    @override_settings(EMAIL_BACKEND="emailtemplates.backends.EmailBackend")
    def test_no_warning_for_the_backend_recording_emails(self):
        self.assertEqual(check_email_backend(None), [])

    @override_settings(
        EMAIL_BACKEND="emailtemplates.tests.test_email_log.LoggingLocMemBackend"
    )
    def test_no_warning_for_a_backend_with_the_mixin(self):
        self.assertEqual(check_email_backend(None), [])

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_no_warning_for_the_backend_of_the_test_runner(self):
        self.assertEqual(check_email_backend(None), [])

    @override_settings(EMAIL_BACKEND="emailtemplates.tests.missing.Backend")
    def test_a_backend_that_cannot_be_imported_does_not_stop_the_checks(self):
        with mock.patch(
            "emailtemplates.checks.import_string", side_effect=RuntimeError("broken")
        ):
            self.assertEqual(check_email_backend(None), [])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_warning_for_another_backend(self):
        # e.g. EMAIL_BACKEND overridden by the settings of an environment
        errors = check_email_backend(None)
        self.assertEqual([error.id for error in errors], ["emailtemplates.W002"])
