# Links betting sessions to CockFightRoundVideo so round ID matches video round (same number).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0036_remove_mp4_variants'),
    ]

    operations = [
        migrations.AddField(
            model_name='cockfightsession',
            name='video_round',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='betting_sessions',
                to='game.cockfightroundvideo',
            ),
        ),
    ]
