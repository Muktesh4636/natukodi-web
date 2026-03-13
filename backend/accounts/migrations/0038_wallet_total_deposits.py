# Migration: Wallet.total_deposits for new withdrawable rule
# Rule: unavailable = max(0, total_deposits - turnover), withdrawable = balance - unavailable

from django.db import migrations, models
from django.db.models import Sum


def backfill_total_deposits(apps, schema_editor):
    """Backfill total_deposits from Transaction: sum(DEPOSIT) per user."""
    Wallet = apps.get_model('accounts', 'Wallet')
    Transaction = apps.get_model('accounts', 'Transaction')
    for wallet in Wallet.objects.all():
        dep_sum = Transaction.objects.filter(
            user_id=wallet.user_id, transaction_type='DEPOSIT'
        ).aggregate(s=Sum('amount'))['s']
        total = dep_sum or 0
        Wallet.objects.filter(pk=wallet.pk).update(total_deposits=int(total))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0037_user_total_referrals_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='total_deposits',
            field=models.BigIntegerField(default=0, help_text='Cumulative deposits (and bonuses) credited. Unavailable = max(0, total_deposits - turnover).'),
        ),
        migrations.RunPython(backfill_total_deposits, noop),
    ]
