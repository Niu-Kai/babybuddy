import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.models import Child, Height, Weight
from dashboard.templatetags.cards import dashboard_latest_measurements


class LatestMeasurementsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "latest-measurements", is_superuser=True
        )
        cls.user.settings.dashboard_hidden_cards = []
        cls.user.settings.length_unit = "in"
        cls.user.settings.weight_unit = "lb"
        cls.user.settings.save()
        cls.a = Child.objects.create(first_name="Alice", birth_date="2020-01-01")
        cls.b = Child.objects.create(first_name="Ben", birth_date="2020-01-01")
        Height.objects.create(
            child=cls.a, date="2020-03-01", height=50, entry_unit="cm"
        )
        cls.latest = Height.objects.create(
            child=cls.a, date="2020-04-01", height=60, entry_unit="cm"
        )
        cls.other = Height.objects.create(
            child=cls.b, date="2020-05-01", height=70, entry_unit="cm"
        )
        Weight.objects.create(
            child=cls.a, date="2020-04-01", time="09:00", weight=5, entry_unit="kg"
        )
        cls.weight = Weight.objects.create(
            child=cls.a, date="2020-04-01", time="10:00", weight=6, entry_unit="kg"
        )

    def test_latest_is_per_child_and_respects_measurement_order(self):
        request = RequestFactory().get("/dashboard/")
        request.user = self.user
        rows = dashboard_latest_measurements({"request": request}, self.a)[
            "measurements"
        ]
        by_field = {row["field"]: row for row in rows}
        self.assertEqual(by_field["height"]["entry"], self.latest)
        self.assertEqual(by_field["weight"]["entry"], self.weight)
        self.assertIsNone(by_field["temperature"]["entry"])
        self.assertEqual(
            by_field["height"]["url"],
            reverse("core:height-list") + "?scope=" + self.a.slug,
        )
        other = dashboard_latest_measurements({"request": request}, self.b)[
            "measurements"
        ]
        self.assertEqual(
            next(row for row in other if row["field"] == "height")["entry"], self.other
        )

    def test_header_placement_units_and_comparison(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.a.slug])
        )
        header = re.search(
            r'<header class="dash-hero">(.*?)</header>', response.content.decode(), re.S
        ).group(1)
        self.assertIn("Latest measurements", header)
        self.assertIn("23.62 in", header)
        self.assertIn("13.23 lbs", header)
        self.assertIn("Apr", header)
        self.assertIn("No entries", header)
        response = self.client.get(reverse("dashboard:dashboard"), {"scope": "compare"})
        headers = re.findall(
            r'<header class="dash-hero">(.*?)</header>', response.content.decode(), re.S
        )
        self.assertEqual(len(headers), 2)
        self.assertTrue(all("Latest measurements" in header for header in headers))
        self.assertTrue(any("27.56 in" in header for header in headers))

    def test_measurements_require_view_permission(self):
        user = get_user_model().objects.create_user("height-only")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_height", content_type__app_label="core"
            )
        )
        request = RequestFactory().get("/dashboard/")
        request.user = user
        rows = dashboard_latest_measurements({"request": request}, self.a)[
            "measurements"
        ]
        self.assertEqual([row["field"] for row in rows], ["height"])
        self.assertEqual(rows[0]["entry"], self.latest)
