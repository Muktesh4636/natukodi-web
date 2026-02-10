# Generated migration to remove bonus wallet and merge balances

from django.db import migrations
from decimal import Decimal


def migrate_bonus_to_main_balance(apps, schema_editor):
    """Move all bonus_balance amounts to main balance"""
    Wallet = apps.get_model('accounts', 'Wallet')
    
    # Add all bonus_balance to balance for each wallet
    for wallet in Wallet.objects.all():
        if wallet.bonus_balance and wallet.bonus_balance > Decimal('0.00'):
            wallet.balance = (wallet.balance or Decimal('0.00')) + wallet.bonus_balance
            wallet.save(update_fields=['balance'])
    
    print(f"Migrated bonus balances to main balance for {Wallet.objects.count()} wallets")


def reverse_migration(apps, schema_editor):
    """Reverse migration - cannot restore bonus_balance values"""
    # Cannot reverse as we don't know which part of balance was bonus
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0023_depositrequest_payment_method_and_more'),
    ]

    operations = [
        # Step 1: Migrate bonus_balance to balance
        migrations.RunPython(migrate_bonus_to_main_balance, reverse_migration),
        
        # Step 2: Remove bonus_balance field
        migrations.RemoveField(
            model_name='wallet',
            name='bonus_balance',
        ),
    ]
