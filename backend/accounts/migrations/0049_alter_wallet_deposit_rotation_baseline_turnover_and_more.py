# Keeps migration graph aligned with servers that generated this leaf alongside referral work.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_franchise_help_social_links'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallet',
            name='deposit_rotation_baseline_turnover',
            field=models.BigIntegerField(
                default=0,
                help_text='Turnover snapshot: unavailable lock decreases by (turnover - baseline).',
            ),
        ),
        migrations.AlterField(
            model_name='wallet',
            name='deposit_rotation_lock',
            field=models.BigIntegerField(
                default=0,
                help_text=(
                    'Amount (deposits/bonuses) still requiring 1x turnover since baseline; '
                    'see apply_deposit_rotation_credit.'
                ),
            ),
        ),
    ]
