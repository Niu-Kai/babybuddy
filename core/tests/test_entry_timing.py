import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import forms, models


class EntryTimingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "entry-controls", is_superuser=True
        )
        cls.user.settings.timezone = "Pacific/Honolulu"
        cls.user.settings.save()
        cls.child = models.Child.objects.create(first_name="A", birth_date="2019-01-01")
        cls.other = models.Child.objects.create(first_name="B", birth_date="2019-01-01")

    def setUp(self):
        self.client.force_login(self.user)
        timezone.activate("Pacific/Honolulu")
        self.addCleanup(timezone.deactivate)

    def test_all_entry_defaults_and_clock_formats(self):
        instant = datetime.datetime(
            2026, 9, 21, 5, 20, 42, tzinfo=datetime.timezone.utc
        )
        names = [
            "feeding",
            "bottle-feeding",
            "pumping",
            "sleep",
            "tummytime",
            "bathtime",
            "diaperchange",
            "medication",
            "reflux",
            "food",
            "note",
            "temperature",
            "timer",
        ]
        for use24, expected in ((False, "07:20 PM"), (True, "19:20")):
            self.user.settings.use_24_hour_time = use24
            self.user.settings.save()
            with patch("django.utils.timezone.now", return_value=instant):
                for name in names:
                    with self.subTest(name=name, use24=use24):
                        response = self.client.get(reverse("core:" + name + "-add"))
                        self.assertEqual(response.status_code, 200)
                        self.assertNotContains(response, 'type="datetime-local"')
                        form = response.context["form"]
                        self.assertEqual(form.initial["appointment_date"], "2026-09-20")
                        self.assertEqual(form.initial["start_time"], expected)
                        self.assertContains(response, "data-appointment-choice")
                for name in ("weight", "height", "head-circumference"):
                    response = self.client.get(reverse("core:" + name + "-add"))
                    self.assertContains(response, 'value="2026-09-20"')
                weight = self.client.get(reverse("core:weight-add"))
                self.assertContains(weight, 'value="' + expected + '"')
                appointment = self.client.get(reverse("core:appointment-add"))
                self.assertEqual(appointment.context["form"].initial["start_time"], "")
                self.assertEqual(
                    appointment.context["form"].initial["appointment_date"],
                    "2026-09-20",
                )

    def test_split_forms_save_local_time_and_calculated_end(self):
        cases = [
            (
                "feeding",
                models.Feeding,
                {
                    "type": "formula",
                    "method": "bottle",
                    "amount": "90",
                    "entry_unit": "mL",
                },
            ),
            ("pumping", models.Pumping, {"amount": "90", "entry_unit": "mL"}),
            ("sleep", models.Sleep, {}),
            ("tummytime", models.TummyTime, {}),
            ("bathtime", models.BathTime, {}),
            ("diaperchange", models.DiaperChange, {"wet": "on"}),
            (
                "medication",
                models.Medication,
                {"name": "Vitamin", "dosage": "1", "dosage_unit": "ml"},
            ),
            ("reflux", models.Reflux, {"severity": "mild"}),
            ("food", models.Food, {"name": "Banana"}),
            ("note", models.Note, {"note": "A note"}),
            (
                "temperature",
                models.Temperature,
                {"temperature": "37", "entry_unit": "C"},
            ),
        ]
        for name, model, extra in cases:
            with self.subTest(name=name):
                data = {
                    "child": self.child.pk,
                    "appointment_date": "2020-03-01",
                    "start_time": "11:45 PM",
                    "duration_minutes": "30",
                    **extra,
                }
                response = self.client.post(reverse("core:" + name + "-add"), data)
                self.assertEqual(
                    response.status_code,
                    302,
                    getattr(response, "context", None)
                    and response.context["form"].errors,
                )
                saved = model.objects.latest("pk")
                start = getattr(saved, "start", None) or saved.time
                self.assertEqual(
                    timezone.localtime(start).isoformat(), "2020-03-01T23:45:00-10:00"
                )
                if hasattr(saved, "end"):
                    self.assertEqual(
                        timezone.localtime(saved.end).isoformat(),
                        "2020-03-02T00:15:00-10:00",
                    )

    def test_edit_preserves_precision_and_duration_changes_work(self):
        start = datetime.datetime(
            2020, 3, 1, 23, 45, 27, tzinfo=ZoneInfo("Pacific/Honolulu")
        )
        end = start + datetime.timedelta(minutes=17, seconds=12)
        saved = models.Sleep.objects.create(child=self.child, start=start, end=end)
        form = forms.SleepForm(instance=saved, user=self.user)
        data = {
            "child": self.child.pk,
            **{
                key: form.initial[key]
                for key in ("appointment_date", "start_time", "duration_minutes")
            },
        }
        form = forms.SleepForm(instance=saved, user=self.user, data=data)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.start, start)
        self.assertEqual(saved.end, end)
        data["duration_minutes"] = "22,5"
        form = forms.SleepForm(instance=saved, user=self.user, data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().end - start, datetime.timedelta(minutes=22.5))

    def test_validation_optional_duration_and_overlap_confirmation(self):
        data = {
            "child": self.child.pk,
            "appointment_date": "2020-03-01",
            "start_time": "13:07",
            "duration_minutes": "",
        }
        feeding = forms.FeedingForm(
            user=self.user, data={**data, "type": "formula", "method": "bottle"}
        )
        self.assertTrue(feeding.is_valid(), feeding.errors)
        self.assertEqual(feeding.save().start, feeding.instance.end)
        for value in ("", "-1", "1e20", "invalid"):
            form = forms.SleepForm(
                user=self.user, data={**data, "duration_minutes": value}
            )
            self.assertFalse(form.is_valid())
            self.assertIn("duration_minutes", form.errors)
        start = datetime.datetime(2020, 3, 1, 13, tzinfo=ZoneInfo("Pacific/Honolulu"))
        models.Sleep.objects.create(
            child=self.child, start=start, end=start + datetime.timedelta(hours=1)
        )
        data["duration_minutes"] = "20"
        form = forms.SleepForm(user=self.user, data=data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.overlap_conflict)
        form = forms.SleepForm(user=self.user, data={**data, "allow_overlap": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

    def test_preview_permissions_and_daylight_saving(self):
        user = get_user_model().objects.create_user("sleep-only")
        user.settings.timezone = "America/New_York"
        user.settings.save()
        user.user_permissions.add(Permission.objects.get(codename="add_sleep"))
        self.client.force_login(user)
        data = {
            "appointment_date": "2020-03-08",
            "start_time": "1:45 AM",
            "duration_minutes": "30",
        }
        response = self.client.get(
            reverse("core:entry-end-preview", args=["sleep"]), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["end"], "2020-03-08T03:15:00-04:00")
        self.assertEqual(
            self.client.get(
                reverse("core:entry-end-preview", args=["pumping"]), data
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("core:entry-end-preview", args=["user"]), data
            ).status_code,
            403,
        )

    def test_preview_preserves_hidden_seconds_and_dst_fold(self):
        data = {
            "appointment_date": "2020-03-01",
            "start_time": "23:45",
            "duration_minutes": "17.5",
            "reference_start": "2020-03-01T23:45:59-10:00",
        }
        response = self.client.get(
            reverse("core:entry-end-preview", args=["sleep"]), data
        )
        self.assertEqual(response.json()["end"], "2020-03-02T00:03:29-10:00")
        # Changing the visible time discards the old timestamp's seconds.
        response = self.client.get(
            reverse("core:entry-end-preview", args=["sleep"]),
            {**data, "start_time": "23:46"},
        )
        self.assertEqual(response.json()["end"], "2020-03-02T00:03:30-10:00")
        self.user.settings.timezone = "America/New_York"
        self.user.settings.save()
        data = {
            "appointment_date": "2020-11-01",
            "start_time": "1:30 AM",
            "duration_minutes": "30",
            "reference_start": "2020-11-01T01:30:00-05:00",
        }
        response = self.client.get(
            reverse("core:entry-end-preview", args=["sleep"]), data
        )
        self.assertEqual(response.json()["end"], "2020-11-01T02:00:00-05:00")

    def test_timer_entry_preserves_timing_and_consumes_only_on_save(self):
        timer = models.Timer.objects.create(
            user=self.user,
            child=self.child,
            start=timezone.now() - datetime.timedelta(minutes=12, seconds=7),
        )
        initial = forms.SleepForm(user=self.user, timer=timer.pk)
        data = {
            "child": self.child.pk,
            **{
                key: initial.initial[key]
                for key in ("appointment_date", "start_time", "duration_minutes")
            },
        }
        invalid = forms.SleepForm(
            user=self.user, timer=timer.pk, data={**data, "duration_minutes": "bad"}
        )
        self.assertFalse(invalid.is_valid())
        timer.refresh_from_db()
        self.assertTrue(timer.active)
        form = forms.SleepForm(user=self.user, timer=timer.pk, data=data)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.start, timer.start)
        self.assertEqual(saved.end, initial.initial["end"])
        self.assertFalse(models.Timer.objects.filter(pk=timer.pk).exists())

    def test_period_filters_on_every_board_and_local_boundaries(self):
        for name in (
            "weight",
            "height",
            "head-circumference",
            "bmi",
            "temperature",
            "feeding",
            "pumping",
            "food",
            "sleep",
            "diaperchange",
            "tummytime",
            "bathtime",
            "medication",
            "reflux",
            "note",
        ):
            response = self.client.get(reverse("core:" + name + "-list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-timeline-filters")
            self.assertContains(response, "data-date-picker")
            self.assertNotContains(response, "Apply dates")
        for child in (self.child, self.other):
            for day in ("2020-03-01", "2020-03-08", "2020-04-01", "2021-03-01"):
                models.Height.objects.create(
                    child=child, date=day, height=50, entry_unit="cm"
                )
        for period, count in (
            ("day", 2),
            ("week", 2),
            ("month", 4),
            ("year", 6),
            ("all", 8),
        ):
            response = self.client.get(
                reverse("core:height-list"),
                {"period": period, "date": "2020-03-01", "scope": "compare"},
            )
            self.assertEqual(response.context["record_count"], count)
            self.assertEqual(
                [
                    panel["page"].paginator.count
                    for panel in response.context["record_panels"]
                ],
                [count // 2] * 2,
            )
        response = self.client.get(
            reverse("core:height-list"), {"period": "month", "date": "invalid"}
        )
        self.assertEqual(response.context["record_count"], 0)
        self.assertTrue(response.context["record_period"].errors)
        for hour in (9, 10):
            models.Note.objects.create(
                child=self.child,
                note=str(hour),
                time=datetime.datetime(
                    2020, 3, 2, hour, 30, tzinfo=datetime.timezone.utc
                ),
            )
        response = self.client.get(
            reverse("core:note-list"),
            {"period": "day", "date": "2020-03-01", "scope": self.child.slug},
        )
        self.assertEqual(response.context["record_count"], 1)
        self.assertEqual(response.context["filter"].qs.get().note, "9")
