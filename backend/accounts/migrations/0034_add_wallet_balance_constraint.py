# Generated manually to add wallet balance non-negative constraint

from django.db import migrations, models


def fix_negative_balances(apps, schema_editor):
    """Fix any existing negative balances before adding constraint"""
    Wallet = apps.get_model('accounts', 'Wallet')
    # Fix negative balances by setting to 0
    Wallet.objects.filter(balance__lt=0).update(balance=0.00)


def reverse_fix_negative_balances(apps, schema_editor):
    """Reverse migration - nothing to do"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0033_paymentmethod_usdt_exchange_rate'),
    ]

    operations = [
        # First, fix any existing negative balances
        migrations.RunPython(fix_negative_balances, reverse_fix_negative_balances),
        # Then, add the constraint
        migrations.AddConstraint(
            model_name='wallet',
            constraint=models.CheckConstraint(
                check=models.Q(('balance__gte', 0)),
                name='wallet_balance_non_negative'
            ),
        ),
    ]
