# Generated migration for Wallet.turnover

from django.db import migrations, models
from django.db.models import Sum


def backfill_turnover(apps, schema_editor):
    """Backfill turnover from Transaction history: sum(BET) - sum(REFUND for bet refunds)"""
    Wallet = apps.get_model('accounts', 'Wallet')
    Transaction = apps.get_model('accounts', 'Transaction')
    for wallet in Wallet.objects.all():
        bet_sum = Transaction.objects.filter(
            user_id=wallet.user_id, transaction_type='BET'
        ).aggregate(s=Sum('amount'))['s']
        refund_sum = Transaction.objects.filter(
            user_id=wallet.user_id, transaction_type='REFUND',
            description__icontains='Refund for removed bet'
        ).aggregate(s=Sum('amount'))['s']
        bet_sum = bet_sum or 0
        refund_sum = refund_sum or 0
        turnover = max(0, int(bet_sum) - int(refund_sum))
        Wallet.objects.filter(pk=wallet.pk).update(turnover=turnover)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_add_wallet_balance_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='turnover',
            field=models.BigIntegerField(default=0, help_text='Total amount wagered. unavaliable = max(0, balance - turnover)'),
        ),
        migrations.RunPython(backfill_turnover, noop),
    ]
