from django.db import migrations

ITEMS = [
    ("documents", "ID, insurance card, and hospital paperwork"),
    ("documents", "Birth preferences and care-team contact details"),
    ("documents", "Phone and long charging cable"),
    ("parent", "Comfortable clothes, robe, and non-slip slippers"),
    ("parent", "Toiletries, glasses, and hair ties"),
    ("parent", "Maternity pads and comfortable underwear"),
    ("parent", "Nursing bra and breast pads, if wanted"),
    ("parent", "Regular medications and an up-to-date medication list"),
    ("parent", "Water bottle and snacks approved by your care team"),
    ("baby", "Going-home clothes in two sizes"),
    ("baby", "Blanket, diapers, and wipes if your hospital requests them"),
    ("baby", "Properly installed rear-facing car seat for the trip home"),
    ("support", "Change of clothes and toiletries"),
    ("support", "Snacks, water, and charger"),
    ("home", "Confirm the hospital entrance, parking, and route"),
    ("home", "Arrange care for other children and pets"),
    ("home", "Keep hospital bags and car-seat instructions ready"),
]


def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model("prebirth", "Plan").objects.using(alias).get_or_create(pk=1)
    model = apps.get_model("prebirth", "ChecklistItem")
    for position, (category, label) in enumerate(ITEMS):
        model.objects.using(alias).get_or_create(
            label=label, category=category, preset=True, defaults={"position": position}
        )


class Migration(migrations.Migration):
    dependencies = [("prebirth", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
