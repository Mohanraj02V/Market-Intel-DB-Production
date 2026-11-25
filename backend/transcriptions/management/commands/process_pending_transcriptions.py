from django.core.management.base import BaseCommand

from transcriptions.services import process_pending_transcriptions


class Command(BaseCommand):
    help = 'Process pending Zoom meeting transcriptions and recover missed webhooks.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-items',
            type=int,
            default=50,
            help='Maximum number of pending transcriptions to check in one run.',
        )

    def handle(self, *args, **options):
        max_items = options['max_items']
        summary = process_pending_transcriptions(max_items=max_items)
        self.stdout.write(
            self.style.SUCCESS(
                f"Pending transcription check complete: "
                f"discovered={summary['discovered']}, "
                f"checked={summary['checked']}, "
                f"completed={summary['completed']}, "
                f"waiting={summary['waiting']}, "
                f"unavailable={summary['unavailable']}, "
                f"failed={summary['failed']}"
            )
        )
