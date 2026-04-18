from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0021_adminpermissions_can_view_game_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerjourney',
            name='is_algo_test',
            field=models.BooleanField(default=False),
        ),
    ]
