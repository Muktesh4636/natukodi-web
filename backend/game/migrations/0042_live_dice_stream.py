from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0041_live_dice_round_video'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveDiceStream',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stream_key', models.CharField(
                    max_length=64, unique=True,
                    help_text='Push to: rtmp://svs.fightening.sbs/live/<stream_key>',
                )),
                ('label', models.CharField(
                    blank=True, default='', max_length=100,
                    help_text='Optional label (e.g. "Round 5 – 10:00 PM").',
                )),
                ('is_live', models.BooleanField(
                    default=False,
                    help_text='True while mediamtx reports an active publisher.',
                )),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('stopped_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='live_dice_streams_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Live Dice Stream',
                'verbose_name_plural': 'Live Dice Streams',
                'ordering': ['-id'],
            },
        ),
    ]
