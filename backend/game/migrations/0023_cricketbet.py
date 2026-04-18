from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0022_playerjourney_is_algo_test'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CricketBet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.BigIntegerField()),
                ('event_name', models.CharField(max_length=255)),
                ('market_id', models.BigIntegerField()),
                ('market_name', models.CharField(max_length=255)),
                ('outcome_id', models.BigIntegerField()),
                ('outcome_name', models.CharField(max_length=255)),
                ('odds', models.DecimalField(decimal_places=2, max_digits=10)),
                ('stake', models.BigIntegerField(help_text='Stake in paise (smallest currency unit)')),
                ('potential_payout', models.BigIntegerField()),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('WON', 'Won'), ('LOST', 'Lost'), ('VOID', 'Void')],
                    default='PENDING',
                    max_length=20,
                )),
                ('payout_amount', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('settled_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cricket_bets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Cricket Bet',
                'verbose_name_plural': 'Cricket Bets',
                'ordering': ['-created_at'],
            },
        ),
    ]
