from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import game.models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0040_cockfight_round_video_odds'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='adminpermissions',
            name='can_upload_live_dice_videos',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='LiveDiceRoundVideo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('video', models.FileField(max_length=255, upload_to=game.models.live_dice_video_upload_path)),
                ('scheduled_start', models.DateTimeField(
                    blank=True, null=True,
                    help_text='Wall-clock time when playback should start for everyone (simulated live).',
                )),
                ('duration_seconds', models.FloatField(
                    blank=True, null=True,
                    help_text='Video length in seconds (ffprobe); used to drop stream URL after broadcast ends.',
                )),
                ('hls_ready', models.BooleanField(
                    default=False,
                    help_text='True once HLS segments have been generated for adaptive streaming.',
                )),
                ('hls_token', models.CharField(
                    blank=True, default='', max_length=64,
                    help_text='Random UUID used as the private HLS directory path.',
                )),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='live_dice_round_videos_uploaded',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Live Dice Round Video',
                'verbose_name_plural': 'Live Dice Round Videos',
                'ordering': ['-id'],
            },
        ),
    ]
