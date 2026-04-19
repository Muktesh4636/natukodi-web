# Generated manually — remove dice control permission field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0026_livestream"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="adminpermissions",
            name="can_control_dice",
        ),
    ]
