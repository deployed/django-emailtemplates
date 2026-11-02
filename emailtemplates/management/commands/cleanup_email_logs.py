# coding=utf-8
from django.core.management.base import BaseCommand

from emailtemplates.history import cleanup_email_logs


class Command(BaseCommand):
    help = (
        "Deletes the sent emails older than the given number of days, the attachments of "
        "sent emails past EMAILTEMPLATES_EMAIL_LOG_ATTACHMENT_RETENTION_DAYS and the "
        "attachment files no email uses; pending and failed ones are kept."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Keep the sent emails of the last DAYS days "
            "(EMAILTEMPLATES_EMAIL_LOG_RETENTION_DAYS, 180 by default).",
        )

    def handle(self, *args, days, **options):
        emails, files = cleanup_email_logs(days)
        self.stdout.write(
            "Deleted %d sent email logs and %d attachment files." % (emails, files)
        )
