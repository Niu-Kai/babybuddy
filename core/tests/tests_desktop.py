from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Child, Feeding, Height, Weight, Temperature
from core.forms import HeightForm, WeightForm, TemperatureForm
from core.units import convert


class DesktopViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "desktop", password="test", is_superuser=True
        )
        cls.a = Child.objects.create(
            first_name="Alice", last_name="One", birth_date="2026-01-01"
        )
        cls.b = Child.objects.create(
            first_name="Ben", last_name="Two", birth_date="2026-01-02"
        )
        cls.now = timezone.now() - timedelta(hours=1)
        for child, offsets in ((cls.a, [5, 3, 0]), (cls.b, [4, 2])):
            for offset in offsets:
                start = cls.now - timedelta(hours=offset)
                Feeding.objects.create(
                    child=child,
                    start=start,
                    end=start,
                    method="bottle",
                    type="formula",
                    amount=120,
                    entry_unit="mL",
                )
            Height.objects.create(
                child=child, date=timezone.localdate(), height=55, entry_unit="cm"
            )
            Height.objects.create(
                child=child,
                date=timezone.localdate() - timedelta(days=7),
                height=54,
                entry_unit="cm",
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_mixed_unit_preferences_apply_independently(self):
        from core.forms import FeedingForm, HeadCircumferenceForm, PumpingForm
        from core.templatetags.presentation import measurement, volume_total
        from django.test import RequestFactory

        settings = self.user.settings
        settings.liquid_unit = "mL"
        settings.length_unit = "in"
        settings.weight_unit = "lb"
        settings.temperature_unit = "F"
        settings.save()
        for form_class, unit in (
            (HeightForm, "in"),
            (HeadCircumferenceForm, "in"),
            (WeightForm, "lb"),
            (TemperatureForm, "F"),
            (FeedingForm, "mL"),
            (PumpingForm, "mL"),
        ):
            with self.subTest(form=form_class):
                self.assertEqual(form_class(user=self.user).initial["entry_unit"], unit)
        for model, unit in (
            ("height", "in"),
            ("weight", "lb"),
            ("temperature", "F"),
            ("feeding", "mL"),
            ("pumping", "mL"),
        ):
            response = self.client.get(reverse("core:" + model + "-list"))
            self.assertEqual(response.context["display_unit"], unit)
        request = RequestFactory().get("/")
        request.user = self.user
        self.assertIn(
            "in", measurement({"request": request}, Height.objects.first(), "height")
        )
        self.assertEqual(volume_total({"request": request}, 120), "120 mL")

    def test_saving_unit_category_resets_only_its_display_overrides(self):
        session = self.client.session
        session["display_unit_height"] = "cm"
        session["display_unit_headcircumference"] = "cm"
        session["display_unit_feeding"] = "fl oz"
        session.save()
        response = self.client.post(
            reverse("babybuddy:user-settings"),
            {
                "language": "en-US",
                "timezone": "UTC",
                "pagination_count": 25,
                "length_unit": "in",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.length_unit, "in")
        self.assertEqual(self.user.settings.liquid_unit, "mL")
        self.assertNotIn("display_unit_height", self.client.session)
        self.assertNotIn("display_unit_headcircumference", self.client.session)
        self.assertEqual(self.client.session["display_unit_feeding"], "fl oz")
        response = self.client.get(reverse("babybuddy:user-settings"))
        for field in ("liquid_unit", "length_unit", "weight_unit", "temperature_unit"):
            self.assertContains(response, 'name="' + field + '"')
        self.assertNotContains(response, 'name="measurement_system"')

    def test_invalid_unit_category_is_rejected_with_settings_form(self):
        response = self.client.post(
            reverse("babybuddy:user-settings"),
            {
                "language": "en-US",
                "timezone": "UTC",
                "pagination_count": 25,
                "liquid_unit": "lb",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("liquid_unit", response.context["form_settings"].errors)
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.liquid_unit, "mL")

    def test_child_scope_follows_navigation_and_prefills_add(self):
        response = self.client.get(reverse("core:feeding-list"), {"scope": self.a.slug})
        self.assertEqual(
            {row.child_id for row in response.context["object_list"]}, {self.a.pk}
        )
        response = self.client.get(reverse("core:height-list"))
        self.assertEqual(
            {row.child_id for row in response.context["object_list"]}, {self.a.pk}
        )
        response = self.client.get(reverse("core:height-add"))
        self.assertEqual(response.context["form"].initial["child"], self.a)
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertRedirects(
            response, reverse("dashboard:dashboard-child", args=[self.a.slug])
        )

    def test_measurement_list_keeps_conversion_without_duplicate_summary(self):
        response = self.client.get(
            reverse("core:height-list"), {"scope": self.a.slug, "unit": "in"}
        )
        self.assertNotContains(response, "Latest matching measurement")
        self.assertContains(response, "21.65 in")

    def test_combined_scope_restores_all_children(self):
        self.client.get(reverse("core:height-list"), {"scope": self.a.slug})
        response = self.client.get(reverse("core:height-list"), {"scope": "all"})
        self.assertEqual(
            {row.child_id for row in response.context["object_list"]},
            {self.a.pk, self.b.pk},
        )
        self.assertFalse(response.context["unique_child"])

    def test_previous_feeding_is_same_child_and_crosses_pages(self):
        self.user.settings.pagination_count = 1
        self.user.settings.save()
        response = self.client.get(reverse("core:feeding-list"))
        entry = response.context["object_list"][0]
        self.assertEqual(entry.child_id, self.a.pk)
        self.assertEqual(entry.start - entry.previous_feeding_start, timedelta(hours=3))
        self.assertContains(response, "Previous feeding")
        self.assertLess(
            response.content.index(b"Previous feeding"),
            response.content.index(b">Start<"),
        )

    def test_comparison_has_independent_child_pages(self):
        self.user.settings.pagination_count = 1
        self.user.settings.save()
        response = self.client.get(
            reverse("core:feeding-list"),
            {"scope": "compare", f"page_child_{self.a.pk}": 2},
        )
        panels = {p["child"].pk: p for p in response.context["record_panels"]}
        self.assertEqual(panels[self.a.pk]["page"].number, 2)
        self.assertEqual(panels[self.b.pk]["page"].number, 1)
        self.assertEqual(panels[self.a.pk]["page"].object_list[0].child_id, self.a.pk)
        self.assertContains(response, f"child={self.a.slug}")
        self.assertContains(response, f"child={self.b.slug}")

    def test_date_filter_is_shared_across_panels(self):
        response = self.client.get(
            reverse("core:height-list"),
            {"scope": "compare", "from": str(timezone.localdate())},
        )
        self.assertEqual(len(response.context["record_panels"]), 2)
        self.assertTrue(
            all(
                p["page"].paginator.count == 1
                for p in response.context["record_panels"]
            )
        )

    def test_comparison_pages_render(self):
        paths = [
            reverse("dashboard:dashboard"),
            reverse("core:timeline"),
            reverse("core:appointment-calendar"),
            reverse("reports:home"),
            reverse("reports:report-height-change-child", args=[self.a.slug]),
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, {"scope": "compare"})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["report_panels"]), 2)

    def test_legacy_measurement_is_not_converted(self):
        Height.objects.create(child=self.a, date=timezone.localdate(), height=22)
        response = self.client.get(reverse("core:height-list"), {"unit": "in"})
        self.assertContains(response, "unit not recorded")
        self.assertContains(response, "21.65 in")
        self.assertContains(response, ">22</span>")

    def test_read_only_user_sees_no_add_or_delete_controls(self):
        reader = get_user_model().objects.create_user("reader")
        reader.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=["view_child", "view_height"],
            )
        )
        self.client.force_login(reader)
        response = self.client.get(reverse("core:height-list"), {"scope": "compare"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="add-entry-menu"')
        self.assertNotContains(response, reverse("core:height-add"))
        self.assertNotContains(response, "Delete entry")

    def test_stale_child_selection_falls_back(self):
        session = self.client.session
        session["child_scope"] = "deleted-child"
        session.save()
        response = self.client.get(reverse("core:height-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["child_scope"], "all")


class UnitEntryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("units", is_superuser=True)
        cls.child = Child.objects.create(
            first_name="Unit", last_name="Test", birth_date="2026-01-01"
        )

    def data(self, **kwargs):
        return {"child": self.child.pk, "date": str(timezone.localdate()), **kwargs}

    def test_weight_in_pounds_is_stored_as_kg_and_round_trips(self):
        form = WeightForm(data=self.data(weight=10, entry_unit="lb"), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertAlmostEqual(instance.weight, 4.5359237)
        self.assertEqual(instance.entry_unit, "lb")
        edit = WeightForm(instance=instance, user=self.user)
        self.assertAlmostEqual(edit.initial["weight"], 10)
        form = WeightForm(
            data=self.data(weight=edit.initial["weight"], entry_unit="lb"),
            instance=instance,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertAlmostEqual(form.save().weight, 4.5359237)

    def test_legacy_height_is_unchanged_until_unit_is_confirmed(self):
        instance = Height.objects.create(
            child=self.child, date=timezone.localdate(), height=20
        )
        form = HeightForm(data=self.data(height=20), instance=instance, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().height, 20)
        self.assertEqual(instance.entry_unit, "")
        form = HeightForm(
            data=self.data(height=20, entry_unit="in"),
            instance=instance,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertAlmostEqual(form.save().height, 50.8)

    def test_temperature_conversion(self):
        form = TemperatureForm(
            data={
                "child": self.child.pk,
                "time": timezone.now().isoformat(),
                "temperature": 98.6,
                "entry_unit": "F",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertAlmostEqual(form.save().temperature, 37)

    def test_unit_choice_is_validated(self):
        form = HeightForm(data=self.data(height=20, entry_unit="lb"), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("entry_unit", form.errors)

    def test_us_fluid_ounces_are_not_weight_ounces(self):
        self.assertAlmostEqual(convert(4, "fl oz", "mL"), 118.29411825)
        self.assertAlmostEqual(convert(16, "oz", "lb"), 1)
