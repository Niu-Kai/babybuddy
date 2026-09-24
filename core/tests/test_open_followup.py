import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import set_script_prefix, reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from core import models, forms, timeline
from core.templatetags.misc import feeding_time_diff_base
from dashboard.templatetags.cards import card_feeding_recent
from reports.graphs.feeding_amounts import feeding_amounts
from reports.views import report_entries


class OpenFollowupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "open-admin", is_staff=True, is_superuser=True
        )
        cls.user.settings.timezone = "UTC"
        cls.user.settings.save()
        cls.child = models.Child.objects.create(
            first_name="Test", birth_date=dt.date(2020, 1, 1)
        )

    def setUp(self):
        timezone.activate("UTC")
        self.addCleanup(timezone.deactivate)
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def data(self, **kwargs):
        return {
            "child": self.child.pk,
            "appointment_date": "2024-01-01",
            "start_time": "12:00",
            "duration_minutes": "15",
            "type": "breast milk",
            "method": "left breast",
            "entry_unit": "mL",
            "top_up_enabled": "on",
            "top_up_reference": "",
            "top_up_date": "2024-01-01",
            "top_up_time": "12:30",
            "top_up_type": "formula",
            "top_up_amount": "60",
            **kwargs,
        }

    def save_feeding(self, **kwargs):
        form = forms.FeedingForm(self.data(**kwargs), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_linked_bottle_one_row_and_original_clock(self):
        entry = self.save_feeding(
            top_up_secondary_type="breast milk", top_up_secondary_amount="30"
        )
        self.assertEqual(models.Feeding.objects.count(), 1)
        self.assertEqual(entry.total_amount, 90)
        self.assertEqual(entry.duration, dt.timedelta(minutes=15))
        self.assertEqual(entry.start.hour, 12)
        self.assertEqual(entry.top_up_at.minute, 30)
        self.assertIn(feeding_time_diff_base({}, entry), (entry.start, entry.end))
        self.assertContains(self.client.get("/feedings/"), "Top-up bottle")
        self.assertContains(
            self.client.get(f"/children/{self.child.slug}/dashboard/"), "Top-up bottle"
        )
        edit = self.client.get(reverse("core:feeding-update", args=[entry.pk]))
        self.assertEqual(edit.status_code, 200)
        self.assertContains(edit, 'name="top_up_time"')

    def test_unit_conversion_edit_and_legacy_preservation(self):
        entry = self.save_feeding(entry_unit="fl oz", top_up_amount="2")
        self.assertAlmostEqual(entry.top_up_amount, 59.147059125)
        form = forms.FeedingForm(
            self.data(entry_unit="fl oz", top_up_amount="2"),
            instance=entry,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertAlmostEqual(entry.top_up_amount, 59.147059125)
        legacy = self.data()
        legacy.pop("top_up_reference")
        legacy.pop("top_up_amount")
        legacy.pop("top_up_type")
        form = forms.FeedingForm(legacy, instance=entry, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertAlmostEqual(form.save().top_up_amount, 59.147059125)

    def test_explicit_remove_and_invalid_top_ups(self):
        entry = self.save_feeding()
        form = forms.FeedingForm(
            self.data(top_up_enabled=""), instance=entry, user=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().top_up_at)
        for changes, field in [
            ({"top_up_time": "11:30"}, "top_up_at"),
            ({"method": "bottle"}, "method"),
            ({"top_up_amount": "-3"}, "top_up_amount"),
            ({"top_up_type": ""}, "top_up_type"),
        ]:
            form = forms.FeedingForm(
                self.data(allow_overlap="on", **changes), user=self.user
            )
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_top_up_dst_requires_occurrence(self):
        with timezone.override("America/New_York"):
            form = forms.FeedingForm(
                self.data(
                    appointment_date="2023-11-05",
                    start_time="00:30",
                    top_up_date="2023-11-05",
                    top_up_time="01:30",
                ),
                user=self.user,
            )
            self.assertFalse(form.is_valid())
            self.assertIn("top_up_occurrence", form.errors)
            form = forms.FeedingForm(
                self.data(
                    appointment_date="2023-11-05",
                    start_time="00:30",
                    top_up_date="2023-11-05",
                    top_up_time="01:30",
                    top_up_occurrence="1",
                ),
                user=self.user,
            )
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save().top_up_at.utcoffset(), dt.timedelta(hours=-5))

    def test_api_roundtrip_and_validation(self):
        payload = {
            "child": self.child.pk,
            "start": "2024-01-01T12:00:00Z",
            "end": "2024-01-01T12:15:00Z",
            "type": "breast milk",
            "method": "left breast",
            "top_up_at": "2024-01-01T12:30:00Z",
            "top_up_type": "formula",
            "top_up_amount": 60,
        }
        response = self.api.post("/api/feedings/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        key = response.data["id"]
        response = self.api.patch(
            f"/api/feedings/{key}/", {"top_up_amount": 90}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(models.Feeding.objects.get(pk=key).total_amount, 90)
        response = self.api.patch(
            f"/api/feedings/{key}/", {"method": "bottle"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_amount_charts_preserve_totals_and_show_each_session(self):
        first = self.save_feeding(
            top_up_secondary_type="breast milk", top_up_secondary_amount="30"
        )
        second = models.Feeding.objects.create(
            child=self.child,
            start=first.start + dt.timedelta(hours=2),
            end=first.start + dt.timedelta(hours=2),
            type="formula",
            method="bottle",
            amount=60,
            entry_unit="mL",
        )
        for group in ("type", "session"):
            with patch(
                "reports.graphs.feeding_amounts.plotly.plot", return_value="<div></div>"
            ) as render:
                feeding_amounts([first, second], group=group)
                figure = render.call_args.args[0]
                self.assertEqual(
                    sum(sum(v or 0 for v in t.y) for t in figure.data), 150
                )
                self.assertEqual(len(figure.data), 2)
                self.assertEqual(figure.data[0].width, 60480000)
                self.assertEqual(figure.data[0].x[0].hour, 12)
                if group == "session":
                    self.assertEqual(figure.data[0].y[0], 90)
                    self.assertIn("Top-up bottle", figure.data[0].customdata[0])
        page = self.client.get(
            reverse("reports:report-feeding-amounts-child", args=[self.child.slug])
            + "?group=session"
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Feeding session")

    def test_overnight_top_up_uses_its_actual_day(self):
        entry = self.save_feeding(
            start_time="23:30", top_up_date="2024-01-02", top_up_time="00:10"
        )
        request = SimpleNamespace(
            user=self.user, GET={"period": "day", "date": "2024-01-02"}
        )
        self.assertEqual(
            list(
                report_entries(
                    models.Feeding, request, include_top_ups=True, child=self.child
                )
            ),
            [entry],
        )
        with patch(
            "reports.graphs.feeding_amounts.plotly.plot", return_value="<div></div>"
        ) as render:
            feeding_amounts(
                [entry],
                first_day=dt.date(2024, 1, 2),
                last_day=dt.date(2024, 1, 2),
                group="session",
            )
            self.assertEqual(render.call_args.args[0].data[0].y[0], 60)
        recent = card_feeding_recent(
            {"request": request},
            self.child,
            end_date=dt.datetime(2024, 1, 2, 12, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(recent["feedings"][0]["total"], 60)
        self.assertEqual(recent["feedings"][0]["count"], 0)
        events = []
        timeline._add_feedings(
            dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc),
            dt.datetime(2024, 1, 2, 23, 59, tzinfo=dt.timezone.utc),
            events,
            self.child,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], self.child.first_name + " · Feeding")
        self.assertEqual(events[0]["top_up_at"], entry.top_up_at)
        self.assertTrue(events[0]["top_up_summary"])

    def test_root_and_subpath_manifest_and_worker(self):
        for prefix in ("", "/babybuddy", "/apps/baby"):
            with self.subTest(prefix=prefix), override_settings(
                FORCE_SCRIPT_NAME=prefix or None, STATIC_URL=prefix + "/static/"
            ):
                response = self.client.get("/app.webmanifest", SCRIPT_NAME=prefix)
                self.assertEqual(response.status_code, 200)
                manifest = json.loads(response.content)
                self.assertEqual(manifest["start_url"], prefix + "/")
                self.assertEqual(manifest["scope"], prefix + "/")
                self.assertTrue(
                    all(
                        s["url"].startswith(prefix + "/") for s in manifest["shortcuts"]
                    )
                )
                self.assertTrue(
                    all(
                        s["src"].startswith(prefix + "/static/")
                        for s in manifest["icons"]
                    )
                )
                worker = self.client.get("/sw.js", SCRIPT_NAME=prefix)
                self.assertEqual(worker["Service-Worker-Allowed"], prefix + "/")
                self.assertContains(worker, f'var APP_ROOT = "{prefix}/"')
                self.assertContains(worker, f'"{prefix}/entries/add/"')
        set_script_prefix("/")

    def test_qr_payload_preserves_application_base(self):
        with override_settings(FORCE_SCRIPT_NAME="/babybuddy"):
            response = self.client.get("/user/add-device/", SCRIPT_NAME="/babybuddy")
            self.assertEqual(response.status_code, 200)
            prefix, payload = response.context["qr_code_data"].split(":", 1)
            self.assertEqual(prefix, "BABYBUDDY-LOGIN")
            data = json.loads(payload)
            self.assertTrue(data["url"].endswith("/babybuddy/"))
            self.assertEqual(data["api_key"], str(self.user.settings.api_key()))
            self.assertEqual(data["session_cookies"], {})
        set_script_prefix("/")
