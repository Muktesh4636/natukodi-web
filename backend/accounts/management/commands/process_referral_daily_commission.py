"""Nightly job: credit referrers from referees' daily wallet loss × tiered rate (Asia/Kolkata day)."""
from django.core.management.base import BaseCommand

from accounts.referral_logic import process_referral_daily_commissions_for_date, yesterday_local_date


class Command(BaseCommand):
    help = (
        'Settle referral commission for one IST calendar day (default: yesterday — the day that just ended). '
        'Recommended schedule: every day at 01:00 IST. Ensure cron TZ is Asia/Kolkata (or set CRON_TZ).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Settlement date YYYY-MM-DD in server calendar (TIME_ZONE). Default: yesterday.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Compute stats without creating rows or crediting wallets.',
        )

    def handle(self, *args, **options):
        from datetime import date as date_cls

        raw = options.get('date')
        if raw:
            try:
                y, m, d = (int(x) for x in raw.split('-'))
                target = date_cls(y, m, d)
            except Exception:
                self.stderr.write(self.style.ERROR(f'Invalid --date {raw!r}; use YYYY-MM-DD'))
                return
        else:
            target = yesterday_local_date()

        dry = bool(options.get('dry_run'))
        stats = process_referral_daily_commissions_for_date(target, dry_run=dry)
        self.stdout.write(str(stats))
        if dry:
            self.stdout.write(self.style.WARNING('Dry run — no DB changes.'))
