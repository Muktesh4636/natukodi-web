# Generated manually for UserDailyTurnover (cached daily leaderboard turnover)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def get_period_date_from_created_at(created_at):
    """Same logic as game.utils.get_leaderboard_period_date (IST 23:00–23:00)."""
    import pytz
    from datetime import timedelta
    ist = pytz.timezone('Asia/Kolkata')
    if created_at.tzinfo is None:
        created_at = ist.localize(created_at)
    now_ist = created_at.astimezone(ist)
    period_anchor = now_ist.replace(hour=23, minute=0, second=0, microsecond=0)
    if now_ist >= period_anchor:
        period_start = period_anchor
    else:
        period_start = period_anchor - timedelta(days=1)
    return period_start.date()


def backfill_daily_turnover(apps, schema_editor):
    """Backfill UserDailyTurnover from Bet: group by (user_id, period_date), sum chip_amount."""
    Bet = apps.get_model('game', 'Bet')
    UserDailyTurnover = apps.get_model('game', 'UserDailyTurnover')
    from django.db.models import Sum
    from collections import defaultdict
    # Aggregate in Python to compute period_date per bet (no DB date truncation by timezone)
    buckets = defaultdict(lambda: 0)
    for bet in Bet.objects.values_list('user_id', 'chip_amount', 'created_at'):
        user_id, amount, created_at = bet
        period_date = get_period_date_from_created_at(created_at)
        buckets[(user_id, period_date)] += amount
    to_create = [
        UserDailyTurnover(user_id=uid, period_date=pd, turnover=tot)
        for (uid, pd), tot in buckets.items()
        if tot > 0
    ]
    UserDailyTurnover.objects.bulk_create(to_create)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0017_bet_leaderboard_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserDailyTurnover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_date', models.DateField(help_text='IST date of the period start (23:00 on this date starts the period).')),
                ('turnover', models.BigIntegerField(default=0, help_text='Sum of chip_amount for this user in this period.')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_turnovers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'User daily turnover (leaderboard)',
                'verbose_name_plural': 'User daily turnovers (leaderboard)',
                'ordering': ['-period_date', '-turnover'],
            },
        ),
        migrations.AddConstraint(
            model_name='userdailyturnover',
            constraint=models.UniqueConstraint(fields=('user', 'period_date'), name='game_userdailyturnover_user_period_date_uniq'),
        ),
        migrations.AddIndex(
            model_name='userdailyturnover',
            index=models.Index(fields=['period_date', '-turnover'], name='udt_period_turnover'),
        ),
        migrations.RunPython(backfill_daily_turnover, noop_reverse),
    ]
