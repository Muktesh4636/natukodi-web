"""
Management command: apply ffmpeg -movflags faststart to all existing
cockfight round videos so browsers can start playing without downloading
the entire file first.

Usage:
    python manage.py faststart_cockfight_videos
    python manage.py faststart_cockfight_videos --dry-run
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Remux cockfight round videos with ffmpeg faststart (moves moov atom to front).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without changing any files.',
        )

    def handle(self, *args, **options):
        from game.models import CockFightRoundVideo
        from game.utils import apply_mp4_faststart, ensure_cockfight_round_video_duration

        dry = options['dry_run']
        qs = CockFightRoundVideo.objects.order_by('id')
        total = qs.count()
        self.stdout.write(f'Found {total} round video(s).')

        fixed = skipped = errors = 0
        for rv in qs:
            if not rv.video:
                self.stdout.write(f'  #{rv.pk}: no file — skip')
                skipped += 1
                continue
            try:
                path = rv.video.path
            except Exception:
                self.stdout.write(f'  #{rv.pk}: cannot resolve path — skip')
                skipped += 1
                continue

            self.stdout.write(f'  #{rv.pk}: {path}')
            if dry:
                self.stdout.write('    [dry-run] would apply faststart')
                continue

            ok = apply_mp4_faststart(path)
            if ok:
                self.stdout.write(self.style.SUCCESS('    faststart applied'))
                fixed += 1
            else:
                self.stdout.write('    skipped (not MP4/MOV or already fast-start or ffmpeg unavailable)')
                skipped += 1

            # Refresh duration after remux
            rv.refresh_from_db()
            rv.duration_seconds = None  # force re-probe
            rv.save(update_fields=['duration_seconds'])
            try:
                ensure_cockfight_round_video_duration(rv)
            except Exception as e:
                self.stdout.write(f'    duration probe failed: {e}')
                errors += 1

        if not dry:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone. fixed={fixed}  skipped={skipped}  errors={errors}'
            ))
        else:
            self.stdout.write('\n[dry-run complete — no files changed]')
