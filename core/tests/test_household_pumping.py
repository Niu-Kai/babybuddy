from datetime import date, datetime, timedelta, timezone as utc
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from core import models
from core.forms import PumpingForm
from core.lactation import overview


class HouseholdPumpingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "household-pumping", is_superuser=True
        )
        self.user.settings.timezone = timezone.get_current_timezone_name()
        self.user.settings.save(update_fields=["timezone"])
        self.client.force_login(self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)
        self.a = models.Child.objects.create(
            first_name="Alex", birth_date=date(2024, 1, 1)
        )
        self.b = models.Child.objects.create(
            first_name="Sam", birth_date=date(2024, 1, 1)
        )

    def pump(self, hours=3, **kwargs):
        return models.Pumping.objects.create(
            start=self.now - timedelta(hours=hours),
            end=self.now - timedelta(hours=hours) + timedelta(minutes=15),
            amount=60,
            entry_unit="mL",
            **kwargs
        )

    def nurse(self, child, hours=2, method="left breast"):
        return models.Feeding.objects.create(
            child=child,
            start=self.now - timedelta(hours=hours),
            end=self.now - timedelta(hours=hours) + timedelta(minutes=10),
            type="breast milk",
            method=method,
        )

    def test_web_create_without_child_and_preserve_legacy_on_edit(self):
        form = PumpingForm(user=self.user)
        self.assertNotIn("child", form.fields)
        start = timezone.localtime(self.now - timedelta(minutes=30))
        response = self.client.post(
            reverse("core:pumping-add"),
            {
                "appointment_date": start.date().isoformat(),
                "start_time": start.strftime("%H:%M"),
                "duration_minutes": 10,
                "amount": 2,
                "entry_unit": "fl oz",
                "side": "both",
            },
        )
        self.assertEqual(response.status_code, 302)
        entry = models.Pumping.objects.get()
        self.assertIsNone(entry.child_id)
        self.assertAlmostEqual(entry.amount, 59.147059125)
        legacy = self.pump(child=self.a)
        form = PumpingForm(
            {
                "start": legacy.start,
                "end": legacy.end,
                "amount": 70,
                "entry_unit": "mL",
                "side": "left",
            },
            instance=legacy,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        legacy.refresh_from_db()
        self.assertEqual(legacy.child_id, self.a.pk)
        self.assertEqual(legacy.amount, 70)
        self.a.delete()
        legacy.refresh_from_db()
        self.assertIsNone(legacy.child_id)

    def test_api_and_timer_create_household_records(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            "/api/pumping/",
            {
                "start": (self.now - timedelta(hours=4)).isoformat(),
                "end": (self.now - timedelta(hours=3)).isoformat(),
                "amount": 50,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["child"])
        timer = models.Timer.objects.create(
            child=self.a, user=self.user, start=self.now - timedelta(minutes=20)
        )
        response = client.post(
            "/api/pumping/", {"timer": timer.pk, "amount": 70}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["child"])

    def test_list_is_household_for_all_scopes_and_filters(self):
        first = self.pump(child=self.a, side="left")
        second = self.pump(hours=2, child=self.b, side="right")
        third = self.pump(hours=1, side="both")
        for scope in (self.a.slug, self.b.slug, "compare", "all"):
            response = self.client.get(reverse("core:pumping-list"), {"scope": scope})
            self.assertEqual(
                {x.pk for x in response.context["object_list"]},
                {first.pk, second.pk, third.pk},
            )
            self.assertNotIn("record_panels", response.context)
            self.assertNotContains(response, 'data-column="child"')
        response = self.client.get(
            reverse("core:pumping-list"), {"side": "right", "scope": self.a.slug}
        )
        self.assertEqual(list(response.context["object_list"]), [second])

    def test_dashboard_has_one_household_panel_and_can_hide_it(self):
        for scope in ("compare", self.a.slug, self.b.slug):
            response = self.client.get(
                reverse("dashboard:dashboard"), {"scope": scope}, follow=True
            )
            self.assertContains(response, 'id="household-lactation"', count=1)
            self.assertNotContains(response, 'data-dashboard-panel="pumping_last"')
        self.user.settings.dashboard_hidden_cards = ["pumping_overview"]
        self.user.settings.save()
        self.assertNotContains(
            self.client.get(reverse("dashboard:dashboard"), follow=True),
            'id="household-lactation"',
        )

    def test_dashboard_and_reports_work_before_child_exists(self):
        models.Child.objects.all().delete()
        self.assertContains(
            self.client.get(reverse("dashboard:dashboard")), "No sessions yet"
        )
        self.assertContains(
            self.client.get(reverse("reports:pumping")), "Pumping & nursing"
        )
        self.assertEqual(self.client.get(reverse("core:pumping-add")).status_code, 200)

    def test_nursing_across_children_resets_combined_reminder_but_bottles_do_not(self):
        pump = self.pump(side="both")
        self.nurse(self.a, hours=2)
        nurse = self.nurse(self.b, hours=1, method="right breast")
        self.nurse(self.b, hours=0.5, method="bottle")
        self.user.settings.pumping_reminder_minutes = 120
        data = overview(self.user)
        self.assertEqual(data["latest_session"], nurse)
        self.assertEqual(data["reminder_due"], nurse.end + timedelta(minutes=120))
        self.assertFalse(data["reminder_ready"])
        self.assertEqual(data["sides"][1]["last"], nurse)
        self.user.settings.pumping_reminder_basis = "pumping"
        self.assertEqual(
            overview(self.user)["reminder_due"], pump.end + timedelta(minutes=120)
        )
        self.assertTrue(overview(self.user)["reminder_ready"])

    def test_reminders_start_disabled_and_settings_are_personal(self):
        self.assertFalse(overview(self.user)["reminder_enabled"])
        url = reverse("core:pumping-reminders")
        response = self.client.post(url, {"enabled": "on", "basis": "combined"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("minutes", response.context["form"].errors)
        self.assertEqual(
            self.client.post(
                url, {"enabled": "on", "minutes": 150, "basis": "combined"}
            ).status_code,
            302,
        )
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.pumping_reminder_minutes, 150)
        self.assertIsNone(overview(self.user)["reminder_due"])
        other = get_user_model().objects.create_user("another-caregiver")
        self.assertIsNone(other.settings.pumping_reminder_minutes)
        self.client.post(url, {"basis": "combined"})
        self.user.settings.refresh_from_db()
        self.assertIsNone(self.user.settings.pumping_reminder_minutes)

    def test_permissions_do_not_leak_pumping_or_nursing(self):
        self.pump(side="left")
        self.nurse(self.a, hours=1)
        limited = get_user_model().objects.create_user("nursing-only")
        limited.user_permissions.add(Permission.objects.get(codename="view_feeding"))
        data = overview(limited)
        self.assertIsNone(data["last_pump"])
        self.assertEqual(data["pumping_count"], 0)
        self.client.force_login(limited)
        for url in ("core:pumping-list", "core:pumping-reminders", "reports:pumping"):
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)

    def test_combined_report_is_one_chart_and_excludes_bottle_sessions(self):
        self.pump(side="left")
        self.nurse(self.a, method="both breasts")
        self.nurse(self.b, hours=1, method="right breast")
        self.nurse(self.b, hours=0.5, method="bottle")
        response = self.client.get(
            reverse("reports:pumping"), {"scope": "compare"}, HTTP_X_REPORT_PARTIAL="1"
        )
        data = response.json()
        self.assertTrue(data["household_page"])
        self.assertEqual(len(data["plots"]), 1)
        names = {trace["name"] for trace in data["plots"][0]["data"]}
        self.assertEqual(names, {"Pumping · left", "Nursing · both", "Nursing · right"})
        self.assertNotIn("report-comparison", data["html"])

    def test_amount_report_combines_children_and_converts_units(self):
        self.pump(child=self.a)
        self.pump(hours=2, child=self.b)
        self.nurse(self.a)
        response = self.client.get(
            reverse("reports:pumping"),
            {"view": "amounts", "unit": "fl oz", "scope": self.a.slug},
            HTTP_X_REPORT_PARTIAL="1",
        )
        plot = response.json()["plots"][0]
        self.assertAlmostEqual(
            sum(plot["data"][0]["y"]), round(120 / 29.5735295625, 2), places=1
        )
        self.assertIn("fl oz", plot["layout"]["yaxis"]["title"]["text"])

    def test_pattern_includes_cross_midnight_sessions_and_local_day_boundaries(self):
        start = datetime(2024, 1, 2, 9, 50, tzinfo=utc.utc)
        models.Pumping.objects.create(
            start=start,
            end=start + timedelta(minutes=30),
            amount=30,
            entry_unit="mL",
            side="both",
        )
        self.user.settings.timezone = "Pacific/Honolulu"
        self.user.settings.save()
        response = self.client.get(
            reverse("reports:pumping"),
            {"period": "day", "date": "2024-01-02"},
            HTTP_X_REPORT_PARTIAL="1",
        )
        plot = response.json()["plots"][0]
        self.assertEqual(list(plot["data"][0]["base"]), [0])
        self.assertEqual(list(plot["data"][0]["y"]), [20])

    def test_nursing_shortcut_overrides_previous_bottle_method(self):
        self.nurse(self.a, method="bottle")
        response = self.client.get(
            reverse("core:feeding-add"),
            {"child": self.a.slug, "method": "both breasts"},
        )
        self.assertEqual(response.context["form"].initial["method"], "both breasts")

    def test_previous_pumping_uses_household_history_outside_filtered_results(self):
        first = self.pump(hours=3, child=self.a, side="left")
        second = self.pump(hours=2, child=self.b, side="right")
        response = self.client.get(reverse("core:pumping-list"), {"side": "right"})
        self.assertEqual(
            response.context["object_list"][0].previous_pumping_start, first.start
        )
        self.assertContains(response, "1\xa0hour earlier")

    def test_no_feeding_permission_removes_nursing_traces(self):
        self.pump(side="both")
        self.nurse(self.a)
        limited = get_user_model().objects.create_user("pumping-only")
        limited.user_permissions.add(Permission.objects.get(codename="view_pumping"))
        self.client.force_login(limited)
        data = self.client.get(
            reverse("reports:pumping"), HTTP_X_REPORT_PARTIAL="1"
        ).json()
        self.assertEqual(
            {trace["name"] for trace in data["plots"][0]["data"]}, {"Pumping · both"}
        )
        self.assertIsNone(overview(limited)["last_nursing"])
