# coding=utf-8
from django.core.management.base import BaseCommand

from emailtemplates.models import EmailLog


class Command(BaseCommand):
    help = (
        "Deletes the sent emails older than the given number of days; pending and failed "
        "ones are kept."
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
        deleted, _ = EmailLog.objects.past_retention(days).delete()
        self.stdout.write("Deleted %d sent email logs." % deleted)
