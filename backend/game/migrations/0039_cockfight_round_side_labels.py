from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0038_cockfight_side_cock1_cock2'),
    ]

    operations = [
        migrations.AddField(
            model_name='cockfightroundvideo',
            name='label_cock1',
            field=models.CharField(blank=True, default='', help_text='Display name for COCK1 in apps (e.g. Red). API bets stay COCK1.', max_length=80),
        ),
        migrations.AddField(
            model_name='cockfightroundvideo',
            name='label_cock2',
            field=models.CharField(blank=True, default='', help_text='Display name for COCK2 in apps (e.g. Black). API bets stay COCK2.', max_length=80),
        ),
    ]
