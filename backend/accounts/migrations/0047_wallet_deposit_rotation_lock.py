# Deposit rotation: each new deposit needs 1x turnover since that credit, even if lifetime turnover already exceeds older deposits.

from django.db import migrations, models


def backfill_rotation_from_legacy(apps, schema_editor):
    Wallet = apps.get_model('accounts', 'Wallet')
    for w in Wallet.objects.all():
        td = int(w.total_deposits or 0) - int(w.total_deposits_at_last_withdraw or 0)
        tt = int(w.turnover or 0) - int(w.turnover_at_last_withdraw or 0)
        # Legacy unavailable = max(0, td - tt). Equivalently: lock - tt = max(0, td - tt) with baseline = t_at_w → lock = max(td, tt).
        w.deposit_rotation_lock = max(td, tt)
        w.deposit_rotation_baseline_turnover = int(w.turnover_at_last_withdraw or 0)
        w.save(update_fields=['deposit_rotation_lock', 'deposit_rotation_baseline_turnover'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0046_wallet_snapshot_at_withdraw'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='deposit_rotation_lock',
            field=models.BigIntegerField(
                default=0,
                help_text='Deposit/bonus amount still requiring 1x turnover before withdrawable.',
            ),
        ),
        migrations.AddField(
            model_name='wallet',
            name='deposit_rotation_baseline_turnover',
            field=models.BigIntegerField(
                default=0,
                help_text='Wallet.turnover snapshot: lock reduces by (current_turnover - this).',
            ),
        ),
        migrations.RunPython(backfill_rotation_from_legacy, noop_reverse),
    ]
