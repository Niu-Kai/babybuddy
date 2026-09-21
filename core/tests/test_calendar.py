import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Appointment, Child


class CalendarViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "calendar-owner", is_superuser=True
        )
        cls.user.settings.timezone = "Pacific/Honolulu"
        cls.user.settings.save()
        cls.child = Child.objects.create(
            first_name="Alice", last_name="Calendar", birth_date="2026-01-01"
        )
        cls.other = Child.objects.create(
            first_name="Ben", last_name="Calendar", birth_date="2026-01-01"
        )
        cls.day = datetime.datetime(2026, 9, 20, tzinfo=ZoneInfo("Pacific/Honolulu"))
        cls.url = reverse("core:appointment-calendar")
        cls.visit = Appointment.objects.create(
            child=cls.child,
            title="Clinic visit",
            start=cls.day + datetime.timedelta(hours=10),
            location="Clinic",
        )
        Appointment.objects.create(
            child=cls.other,
            title="Other child visit",
            start=cls.day + datetime.timedelta(hours=14),
        )
        Appointment.objects.create(
            child=cls.child,
            title="Earlier week",
            start=cls.day - datetime.timedelta(days=1),
        )

    def setUp(self):
        self.addCleanup(timezone.deactivate)
        self.client.force_login(self.user)

    def test_default_month_heading_and_legacy_month_link(self):
        response = self.client.get(self.url)
        self.assertContains(response, "<h1>Calendar</h1>", html=True)
        self.assertEqual(response.context["period"], "month")
        self.assertContains(response, "data-date-picker")
        response = self.client.get(self.url, {"month": "2024-02"})
        self.assertEqual(response.context["range_end"], datetime.date(2024, 2, 29))
        days = [
            day
            for week in response.context["calendar_month"]["weeks"]
            for day in week
            if day
        ]
        self.assertEqual(len(days), 29)
        self.assertContains(response, "February 2024")

    def test_week_child_scope_and_navigation(self):
        response = self.client.get(
            self.url, {"period": "week", "date": "2026-09-23", "scope": self.child.slug}
        )
        self.assertEqual(response.context["range_start"], datetime.date(2026, 9, 20))
        self.assertEqual(response.context["range_end"], datetime.date(2026, 9, 26))
        self.assertEqual(len(response.context["calendar_days"]), 7)
        self.assertContains(response, "Clinic visit")
        self.assertNotContains(response, "Other child visit")
        self.assertNotContains(response, "Earlier week")
        next_url = response.context["next_period_url"]
        self.assertIn("scope=" + self.child.slug, next_url)
        next_page = self.client.get(self.url + next_url)
        self.assertEqual(next_page.context["range_start"], datetime.date(2026, 9, 27))
        self.assertContains(response, "child=" + self.child.slug)

    def test_year_overview_and_day_drilldown_preserve_scope(self):
        response = self.client.get(
            self.url, {"period": "year", "date": "2026-09-20", "scope": "compare"}
        )
        months = response.context["calendar_months"]
        self.assertEqual(len(months), 12)
        self.assertEqual(months[8]["count"], 3)
        month_page = self.client.get(self.url + months[8]["url"])
        self.assertEqual(month_page.context["period"], "month")
        self.assertContains(month_page, "Clinic visit")
        self.assertContains(month_page, "Other child visit")
        day = next(
            day
            for week in months[8]["weeks"]
            for day in week
            if day and day["date"].day == 20
        )
        day_page = self.client.get(self.url + day["url"])
        self.assertEqual(day_page.context["period"], "day")
        self.assertContains(day_page, "Clinic visit")
        self.assertContains(day_page, "Other child visit")

    def test_overlapping_appointment_shows_continuation_but_midnight_end_is_exclusive(
        self,
    ):
        Appointment.objects.create(
            child=self.child,
            title="Overnight visit",
            start=self.day - datetime.timedelta(hours=1),
            end=self.day + datetime.timedelta(hours=1),
        )
        Appointment.objects.create(
            child=self.child,
            title="Ends at midnight",
            start=self.day - datetime.timedelta(hours=2),
            end=self.day,
        )
        response = self.client.get(
            self.url, {"period": "day", "date": "2026-09-20", "scope": self.child.slug}
        )
        self.assertContains(response, "Overnight visit")
        self.assertContains(response, "Continues")
        self.assertNotContains(response, "Ends at midnight")
        self.assertEqual(response.context["appointment_count"], 2)

    def test_read_only_view_and_permissions(self):
        user = get_user_model().objects.create_user("calendar-reader")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="view_appointment"
            )
        )
        response = self.client.get(self.url, {"period": "day", "date": "2026-09-20"})
        self.assertContains(response, "Clinic visit")
        self.assertNotContains(
            response, reverse("core:appointment-update", args=[self.visit.pk])
        )
        self.assertNotContains(response, "Add Appointment")

    def test_invalid_filters_and_boundary_years(self):
        for params in ({"period": "all"}, {"period": "month", "date": "bad"}):
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["calendar_filter"].errors)
            self.assertNotContains(response, "Clinic visit")
        for date in ("0001-01-01", "9999-12-31"):
            response = self.client.get(self.url, {"period": "month", "date": date})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["calendar_filter"].errors)

    def test_saved_locations_are_suggestions_and_manual_values_remain_valid(self):
        from core.forms import AppointmentForm

        Appointment.objects.create(
            child=self.child, title="First", start=self.day, location=" Kaiser Clinic "
        )
        Appointment.objects.create(
            child=self.other,
            title="Second",
            start=self.day + datetime.timedelta(days=1),
            location="kaiser clinic",
        )
        form = AppointmentForm(user=self.user)
        suggestions = form.fields["location"].widget.locations
        self.assertEqual(
            sum(location.casefold() == "kaiser clinic" for location in suggestions), 1
        )
        self.assertIn("Clinic", suggestions)
        html = str(form["location"])
        self.assertIn('list="id_location_suggestions"', html)
        self.assertIn('<datalist id="id_location_suggestions">', html)
        form = AppointmentForm(
            user=self.user,
            data={
                "child": self.child.pk,
                "title": "New location",
                "start": self.day.isoformat(),
                "location": "A completely new clinic",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().location, "A completely new clinic")

    def test_saved_locations_require_appointment_view_permission(self):
        from core.forms import AppointmentForm

        user = get_user_model().objects.create_user("no-location-history")
        form = AppointmentForm(user=user)
        self.assertEqual(form.fields["location"].widget.locations, ())
        self.assertNotIn("datalist", str(form["location"]))

    def test_appointment_uses_separate_date_time_and_duration(self):
        response = self.client.get(reverse("core:appointment-add"))
        self.assertContains(response, 'name="appointment_date"')
        self.assertContains(response, 'name="start_time"')
        self.assertContains(response, 'name="duration_minutes"')
        self.assertNotContains(response, 'type="datetime-local"')
        self.assertEqual(response.context["form"].initial["duration_minutes"], 30)
        response = self.client.post(
            reverse("core:appointment-add"),
            {
                "child": self.child.pk,
                "title": "Late checkup",
                "appointment_date": "2026-09-20",
                "start_time": "23:45",
                "duration_minutes": 30,
            },
        )
        self.assertEqual(response.status_code, 302)
        saved = Appointment.objects.get(title="Late checkup")
        self.assertEqual(
            timezone.localtime(saved.end).isoformat(), "2026-09-21T00:15:00-10:00"
        )
        self.assertEqual(saved.end - saved.start, datetime.timedelta(minutes=30))

    def test_appointment_edit_preserves_times_and_unknown_duration(self):
        from core.forms import AppointmentForm

        with timezone.override("Pacific/Honolulu"):
            self.visit.start = self.day + datetime.timedelta(hours=10, seconds=15)
            self.visit.end = self.visit.start + datetime.timedelta(
                minutes=45, seconds=30
            )
            self.visit.save()
            original_start, original_end = self.visit.start, self.visit.end
            form = AppointmentForm(instance=self.visit, user=self.user)
            self.assertEqual(form.initial["duration_minutes"], 45.5)
            self.assertNotIn(":15", form.initial["start_time"])
            submitted = {
                "child": self.child.pk,
                "title": self.visit.title,
                **{
                    name: form.initial[name]
                    for name in ("appointment_date", "start_time", "duration_minutes")
                },
            }
            edit = AppointmentForm(instance=self.visit, user=self.user, data=submitted)
            self.assertTrue(edit.is_valid(), edit.errors)
            saved = edit.save()
            self.assertEqual(saved.start, original_start)
            self.assertEqual(saved.end, original_end)
            submitted["duration_minutes"] = ""
            edit = AppointmentForm(instance=saved, user=self.user, data=submitted)
            self.assertTrue(edit.is_valid(), edit.errors)
            self.assertIsNone(edit.save().end)

    def test_appointment_clock_preference_and_both_input_formats(self):
        self.visit.start = self.day + datetime.timedelta(
            hours=13, minutes=30, seconds=42
        )
        self.visit.save()
        for use_24_hour, displayed in ((False, "01:30 PM"), (True, "13:30")):
            self.user.settings.use_24_hour_time = use_24_hour
            self.user.settings.save()
            response = self.client.get(
                reverse("core:appointment-update", args=[self.visit.pk])
            )
            self.assertContains(response, 'value="' + displayed + '"')
            self.assertNotIn("13:30:42", str(response.context["form"]["start_time"]))
            self.assertNotContains(response, 'step="any" name="start_time"')
            for entered, expected in (
                ("1:30 PM", 13),
                ("13:30", 13),
                ("12:30 AM", 0),
                ("12:30 PM", 12),
            ):
                params = {
                    "appointment_date": "2026-09-20",
                    "start_time": entered,
                    "duration_minutes": 30,
                }
                preview = self.client.get(
                    reverse("core:appointment-end-preview"), params
                )
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(
                    datetime.datetime.fromisoformat(preview.json()["end"]).hour,
                    expected + 1,
                )
                response = self.client.post(
                    reverse("core:appointment-add"),
                    {
                        **params,
                        "child": self.child.pk,
                        "title": "Clock format check",
                    },
                )
                self.assertEqual(response.status_code, 302)
                saved = Appointment.objects.filter(title="Clock format check").latest(
                    "pk"
                )
                self.assertEqual(timezone.localtime(saved.start).hour, expected)
                self.assertEqual(saved.start.second, 0)
        for invalid in ("13:30:42", "25:00", "1:30 XM"):
            response = self.client.get(
                reverse("core:appointment-end-preview"),
                {
                    "appointment_date": "2026-09-20",
                    "start_time": invalid,
                    "duration_minutes": 30,
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_appointment_pickers_allow_custom_values_and_unknown_duration(self):
        for use_24_hour, expected in ((False, "01:30 PM"), (True, "13:30")):
            self.user.settings.use_24_hour_time = use_24_hour
            self.user.settings.save()
            response = self.client.get(reverse("core:appointment-add"))
            form = response.context["form"]
            self.assertEqual(len(form.fields["start_time"].widget.choices), 96)
            self.assertIn(
                (expected, expected), form.fields["start_time"].widget.choices
            )
            self.assertContains(response, 'data-choice-value="60"')
            self.assertContains(response, 'aria-label="Choose a duration"')
            self.assertContains(response, 'type="date"')
        params = {
            "appointment_date": "2026-09-20",
            "start_time": "13:07",
            "duration_minutes": "22.5",
        }
        response = self.client.post(
            reverse("core:appointment-add"),
            {
                **params,
                "child": self.child.pk,
                "title": "Custom picker values",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved = Appointment.objects.get(title="Custom picker values")
        self.assertEqual(timezone.localtime(saved.start).strftime("%H:%M"), "13:07")
        self.assertEqual(saved.end - saved.start, datetime.timedelta(minutes=22.5))
        preview = self.client.get(
            reverse("core:appointment-end-preview"), {**params, "duration_minutes": ""}
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIsNone(preview.json()["end"])

    def test_appointment_duration_validation_and_daylight_saving_preview(self):
        self.user.settings.timezone = "America/New_York"
        self.user.settings.save()
        params = {
            "appointment_date": "2026-03-08",
            "start_time": "01:45",
            "duration_minutes": "30",
        }
        count = Appointment.objects.count()
        response = self.client.get(reverse("core:appointment-end-preview"), params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["end"], "2026-03-08T03:15:00-04:00")
        self.assertEqual(Appointment.objects.count(), count)
        response = self.client.post(
            reverse("core:appointment-add"),
            {**params, "child": self.child.pk, "title": "DST appointment"},
        )
        self.assertEqual(response.status_code, 302)
        saved = Appointment.objects.get(title="DST appointment")
        self.assertEqual(saved.end - saved.start, datetime.timedelta(minutes=30))
        for minutes in ("-1", "1e20", "invalid"):
            response = self.client.get(
                reverse("core:appointment-end-preview"),
                {**params, "duration_minutes": minutes},
            )
            self.assertEqual(response.status_code, 400)

    def test_appointment_end_preview_requires_edit_or_add_permission(self):
        user = get_user_model().objects.create_user("no-appointment-preview")
        self.client.force_login(user)
        response = self.client.get(
            reverse("core:appointment-end-preview"),
            {
                "appointment_date": "2026-09-20",
                "start_time": "10:00",
                "duration_minutes": 30,
            },
        )
        self.assertEqual(response.status_code, 403)
