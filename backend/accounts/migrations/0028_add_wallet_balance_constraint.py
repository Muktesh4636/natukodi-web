# Generated manually to add wallet balance non-negative constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0033_paymentmethod_usdt_exchange_rate'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='wallet',
            constraint=models.CheckConstraint(
                check=models.Q(('balance__gte', 0)),
                name='wallet_balance_non_negative'
            ),
        ),
    ]
