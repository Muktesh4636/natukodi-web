# Unavailable = max(0, deposits_since_last_withdraw - turnover_since_last_withdraw).
# Snapshot total_deposits and turnover when a withdrawal is approved.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0045_paymentmethod_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='total_deposits_at_last_withdraw',
            field=models.BigIntegerField(default=0, help_text='Snapshot of total_deposits when last withdrawal was approved. Unavailable = max(0, (total_deposits - this) - (turnover - turnover_at_last_withdraw)).'),
        ),
        migrations.AddField(
            model_name='wallet',
            name='turnover_at_last_withdraw',
            field=models.BigIntegerField(default=0, help_text='Snapshot of turnover when last withdrawal was approved.'),
        ),
    ]
