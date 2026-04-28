from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0030_add_cockfight_videos_permission'),
    ]

    operations = [
        migrations.AddField(
            model_name='cockfightroundvideo',
            name='scheduled_start',
            field=models.DateTimeField(
                blank=True,
                help_text='When the video should begin for all users (simulated live).',
                null=True,
            ),
        ),
    ]
