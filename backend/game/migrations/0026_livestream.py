from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0025_cockfight'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveStream',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Live Stream', max_length=200)),
                ('is_live', models.BooleanField(default=False)),
                ('offer_sdp', models.TextField(blank=True, default='')),
                ('answer_sdp', models.TextField(blank=True, default='')),
                ('broadcaster_candidates', models.TextField(blank=True, default='[]')),
                ('viewer_candidates', models.TextField(blank=True, default='[]')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
