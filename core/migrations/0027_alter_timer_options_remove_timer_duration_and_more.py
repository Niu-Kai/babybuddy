from django.db import migrations


def delete_inactive_timers(apps, schema_editor):
    # Use the historical model: the live one may have columns that do not
    # exist yet at this point in the migration history.
    Timer = apps.get_model("core", "Timer")
    for timer in Timer.objects.filter(active=False):
        timer.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_alter_feeding_end_alter_feeding_start_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="timer",
            options={
                "default_permissions": ("view", "add", "change", "delete"),
                "ordering": ["-start"],
                "verbose_name": "Timer",
                "verbose_name_plural": "Timers",
            },
        ),
        migrations.RemoveField(
            model_name="timer",
            name="duration",
        ),
        migrations.RemoveField(
            model_name="timer",
            name="end",
        ),
        migrations.RunPython(
            delete_inactive_timers, reverse_code=migrations.RunPython.noop
        ),
    ]
