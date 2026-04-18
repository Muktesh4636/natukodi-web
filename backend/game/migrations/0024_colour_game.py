from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0023_cricketbet'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ColourRound',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_id', models.CharField(max_length=50, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('BETTING', 'Betting Open'),
                        ('CLOSED', 'Betting Closed'),
                        ('RESULT', 'Result Announced'),
                        ('COMPLETED', 'Completed'),
                    ],
                    default='BETTING',
                    max_length=20,
                )),
                ('result', models.CharField(
                    blank=True,
                    choices=[
                        ('red', 'Red'),
                        ('green', 'Green'),
                        ('red_violet', 'Red & Violet'),
                        ('green_violet', 'Green & Violet'),
                    ],
                    max_length=20,
                    null=True,
                )),
                ('number', models.IntegerField(blank=True, help_text='Result number 0-9', null=True)),
                ('start_time', models.DateTimeField(auto_now_add=True)),
                ('close_time', models.DateTimeField(blank=True, null=True)),
                ('result_time', models.DateTimeField(blank=True, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Colour Round',
                'verbose_name_plural': 'Colour Rounds',
                'ordering': ['-start_time'],
            },
        ),
        migrations.CreateModel(
            name='ColourBet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bet_on', models.CharField(
                    choices=[
                        ('red', 'Red'),
                        ('green', 'Green'),
                        ('violet', 'Violet'),
                        ('number', 'Number'),
                    ],
                    help_text='"red","green","violet" or "number"',
                    max_length=10,
                )),
                ('number', models.IntegerField(blank=True, help_text='0-9, only when bet_on=number', null=True)),
                ('amount', models.BigIntegerField()),
                ('payout', models.BigIntegerField(default=0)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('WON', 'Won'), ('LOST', 'Lost')],
                    default='PENDING',
                    max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('settled_at', models.DateTimeField(blank=True, null=True)),
                ('round', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='bets',
                    to='game.colourround',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='colour_bets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Colour Bet',
                'verbose_name_plural': 'Colour Bets',
                'ordering': ['-created_at'],
            },
        ),
    ]
