from django.core.management.base import BaseCommand

from transcriptions.services import backfill_historical_transcriptions


class Command(BaseCommand):
    help = (
        'Idempotently backfill historical transcripts from prospects.Meeting, '
        'accounts.CalendarEventRecording, and accounts.MeetingAutomationJob '
        'into transcriptions.MeetingTranscription.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show how many records would be created/updated without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        stats = backfill_historical_transcriptions(dry_run=dry_run)
        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Backfill complete: "
                f"created={stats['created']}, "
                f"updated={stats['updated']}, "
                f"skipped={stats['skipped']}"
            )
        )
