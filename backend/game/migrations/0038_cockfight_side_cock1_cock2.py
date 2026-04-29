# Data migration: Meron/Wala → Cock 1 / Cock 2

from django.db import migrations


def forwards(apps, schema_editor):
    CockFightBet = apps.get_model('game', 'CockFightBet')
    CockFightSession = apps.get_model('game', 'CockFightSession')
    CockFightBet.objects.filter(side='MERON').update(side='COCK1')
    CockFightBet.objects.filter(side='WALA').update(side='COCK2')
    CockFightSession.objects.filter(winner='MERON').update(winner='COCK1')
    CockFightSession.objects.filter(winner='WALA').update(winner='COCK2')


def backwards(apps, schema_editor):
    CockFightBet = apps.get_model('game', 'CockFightBet')
    CockFightSession = apps.get_model('game', 'CockFightSession')
    CockFightBet.objects.filter(side='COCK1').update(side='MERON')
    CockFightBet.objects.filter(side='COCK2').update(side='WALA')
    CockFightSession.objects.filter(winner='COCK1').update(winner='MERON')
    CockFightSession.objects.filter(winner='COCK2').update(winner='WALA')


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0037_cockfight_session_video_round'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
