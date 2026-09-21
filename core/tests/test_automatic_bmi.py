from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import BMI, Child, Height, Weight
from core.bmi import current_bmi
from core.forms import HeightForm, WeightForm


class AutomaticBMITest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("auto-bmi", is_superuser=True)
        self.client.force_login(self.user)
        self.child = Child.objects.create(first_name="Alice", birth_date="2019-01-01")
        self.other = Child.objects.create(first_name="Ben", birth_date="2019-01-01")

    def test_latest_measurements_updates_backdating_and_deletes(self):
        weight = Weight.objects.create(
            child=self.child, date="2020-01-01", weight=5, entry_unit="kg"
        )
        self.assertIsNone(current_bmi(self.child))
        height = Height.objects.create(
            child=self.child, date="2020-01-02", height=50, entry_unit="cm"
        )
        self.assertEqual(current_bmi(self.child).bmi, 20)
        newer = Weight.objects.create(
            child=self.child, date="2020-01-03", time="12:00", weight=6, entry_unit="kg"
        )
        self.assertEqual(current_bmi(self.child).bmi, 24)
        Weight.objects.create(
            child=self.child,
            date="2020-01-03",
            time="09:00",
            weight=5.5,
            entry_unit="kg",
        )
        self.assertEqual(current_bmi(self.child).source_weight, newer)
        Height.objects.create(
            child=self.child, date="2019-12-31", height=40, entry_unit="cm"
        )
        self.assertEqual(current_bmi(self.child).source_height, height)
        height.height = 60
        height.save()
        self.assertAlmostEqual(current_bmi(self.child).bmi, 6 / 0.6**2)
        newer.delete()
        self.assertAlmostEqual(current_bmi(self.child).bmi, 5.5 / 0.6**2)
        height.delete()
        self.assertAlmostEqual(current_bmi(self.child).bmi, 5.5 / 0.4**2)
        self.assertIsNone(current_bmi(self.other))
        self.child.delete()
        self.assertFalse(BMI.objects.exists())

    def test_unknown_units_invalid_values_and_child_changes(self):
        weight = Weight.objects.create(
            child=self.child, date="2020-01-01", weight=5, entry_unit="kg"
        )
        height = Height.objects.create(child=self.child, date="2020-01-01", height=50)
        self.assertIsNone(current_bmi(self.child))
        height.entry_unit = "cm"
        height.save()
        self.assertEqual(current_bmi(self.child).bmi, 20)
        height.height = 0
        height.save()
        self.assertIsNone(current_bmi(self.child))
        height.height = 50
        height.save()
        weight.child = self.other
        weight.save()
        self.assertIsNone(current_bmi(self.child))
        Height.objects.create(
            child=self.other, date="2020-01-01", height=100, entry_unit="cm"
        )
        self.assertEqual(current_bmi(self.other).bmi, 5)

    def test_imperial_form_input_uses_canonical_values(self):
        weight = WeightForm(
            user=self.user,
            data={
                "child": self.child.pk,
                "date": "2020-01-01",
                "weight": "10",
                "entry_unit": "lb",
            },
        )
        self.assertTrue(weight.is_valid(), weight.errors)
        weight.save()
        height = HeightForm(
            user=self.user,
            data={
                "child": self.child.pk,
                "date": "2020-01-01",
                "height": "20",
                "entry_unit": "in",
            },
        )
        self.assertTrue(height.is_valid(), height.errors)
        height.save()
        self.assertAlmostEqual(current_bmi(self.child).bmi, 4.5359237 / 0.508**2)

    def test_legacy_bmi_preserved_but_manual_routes_are_read_only(self):
        legacy = BMI.objects.create(child=self.child, date="2020-01-01", bmi=99)
        Weight.objects.create(
            child=self.child, date="2020-01-01", weight=5, entry_unit="kg"
        )
        Height.objects.create(
            child=self.child, date="2020-01-01", height=50, entry_unit="cm"
        )
        response = self.client.get(reverse("core:bmi-list"))
        self.assertEqual(
            list(response.context["filter"].qs.values_list("bmi", flat=True)), [20]
        )
        self.assertNotContains(response, "Add BMI")
        self.assertNotContains(response, "record-delete")
        for route, args in (
            ("bmi-add", []),
            ("bmi-update", [legacy.pk]),
            ("bmi-delete", [legacy.pk]),
        ):
            self.assertEqual(
                self.client.post(
                    reverse("core:" + route, args=args), {"bmi": 1}
                ).status_code,
                405,
            )
        legacy.refresh_from_db()
        self.assertEqual(legacy.bmi, 99)

    def test_backfill_preserves_manual_records_and_uses_measurement_history(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection

        legacy = BMI.objects.create(child=self.child, date="2020-01-01", bmi=99)
        Weight.objects.create(
            child=self.child, date="2020-01-01", weight=5, entry_unit="kg"
        )
        Height.objects.create(
            child=self.child, date="2020-01-02", height=50, entry_unit="cm"
        )
        Weight.objects.create(
            child=self.child, date="2020-01-03", weight=6, entry_unit="kg"
        )
        BMI.objects.filter(is_calculated=True).delete()
        migration = import_module("core.migrations.0051_automatic_bmi_sources")
        migration.populate_bmi(apps, SimpleNamespace(connection=connection))
        self.assertEqual(
            list(
                BMI.objects.filter(is_calculated=True)
                .order_by("date")
                .values_list("bmi", flat=True)
            ),
            [20, 24],
        )
        self.assertEqual(current_bmi(self.child).bmi, 24)
        legacy.refresh_from_db()
        self.assertEqual(legacy.bmi, 99)
