# Migration: add total_referrals_count to User and backfill from referred_by

from django.db import migrations, models


def backfill_total_referrals_count(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.all():
        count = User.objects.filter(referred_by=user).count()
        User.objects.filter(pk=user.pk).update(total_referrals_count=count)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0036_add_device_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='total_referrals_count',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(backfill_total_referrals_count, noop),
    ]
