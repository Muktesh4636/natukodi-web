# Generated manually
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('game', '0011_alter_bet_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoundPrediction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.IntegerField()),
                ('is_correct', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('round', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='predictions', to='game.gameround')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='round_predictions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='roundprediction',
            constraint=models.UniqueConstraint(fields=('user', 'round'), name='unique_user_round_prediction'),
        ),
    ]
