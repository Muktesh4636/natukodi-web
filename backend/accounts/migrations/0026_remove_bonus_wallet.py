# Generated migration to remove bonus wallet and merge balances

from django.db import migrations
from decimal import Decimal


def migrate_bonus_to_main_balance(apps, schema_editor):
    """Move all bonus_balance amounts to main balance"""
    from django.db import connection
    
    # Check if bonus_balance column exists in database (SQLite compatible)
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(accounts_wallet)")
            columns = [row[1] for row in cursor.fetchall()]
            column_exists = 'bonus_balance' in columns
        else:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='accounts_wallet' AND column_name='bonus_balance'
            """)
            column_exists = cursor.fetchone() is not None
    
    if column_exists:
        # Use raw SQL to access bonus_balance since it might not be in model state
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, balance, bonus_balance FROM accounts_wallet WHERE bonus_balance > 0")
            rows = cursor.fetchall()
            
            for wallet_id, balance, bonus_balance in rows:
                new_balance = (balance or Decimal('0.00')) + bonus_balance
                cursor.execute(
                    "UPDATE accounts_wallet SET balance = %s WHERE id = %s",
                    [new_balance, wallet_id]
                )
        
        print(f"Migrated bonus balances to main balance for {len(rows)} wallets")
    else:
        print("bonus_balance column does not exist in database, skipping data migration")


def remove_bonus_balance_column(apps, schema_editor):
    """Remove bonus_balance column from database if it exists"""
    from django.db import connection
    
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(accounts_wallet)")
            columns = [row[1] for row in cursor.fetchall()]
            column_exists = 'bonus_balance' in columns
        else:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='accounts_wallet' AND column_name='bonus_balance'
            """)
            column_exists = cursor.fetchone() is not None
    
    if column_exists:
        if connection.vendor == 'sqlite':
            # SQLite doesn't support DROP COLUMN easily in older versions, 
            # but Django's schema editor handles it if we use migrations.RemoveField.
            # However, since we are doing it manually to avoid state issues:
            print("SQLite detected. Column removal skipped in RunPython to avoid complexity. "
                  "It will be handled by Django's field removal if added to operations.")
        else:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE accounts_wallet DROP COLUMN bonus_balance;")
            print("Removed bonus_balance column from database")
    else:
        print("bonus_balance column does not exist, skipping removal")


def reverse_migration(apps, schema_editor):
    """Reverse migration - cannot restore bonus_balance values"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0023_depositrequest_payment_method_and_more'),
    ]

    operations = [
        # Step 1: Migrate bonus_balance to balance
        migrations.RunPython(migrate_bonus_to_main_balance, reverse_migration),
        
        # Step 2: Remove bonus_balance column from database only
        # Skip state operation since field is already removed from model
        migrations.RunPython(remove_bonus_balance_column, reverse_migration),
    ]
