import datetime
from django.test import TestCase
from django.utils import timezone
from core import models
from core.timeline import get_objects


class TimelineTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.child = models.Child.objects.create(
            first_name="Test", last_name="Child", birth_date=timezone.now().date()
        )

    def test_cross_midnight_events(self):
        """Overnight sessions appear once, with their full range on either day."""
        day_1 = timezone.make_aware(datetime.datetime(2023, 1, 1))
        day_2 = timezone.make_aware(datetime.datetime(2023, 1, 2))

        start_time = day_1.replace(hour=23, minute=0)
        end_time = day_2.replace(hour=1, minute=0)

        models_to_test = [
            models.Sleep,
            models.TummyTime,
            models.Feeding,
        ]

        for model in models_to_test:
            with self.subTest(model=model.__name__):
                create_kwargs = {
                    "child": self.child,
                    "start": start_time,
                    "end": end_time,
                }
                if model is models.Feeding:
                    create_kwargs.update(type="formula", method="bottle")
                instance = model.objects.create(**create_kwargs)

                events_day_1 = get_objects(date=day_1, child=self.child)
                events_day_2 = get_objects(date=day_2, child=self.child)

                for events in (events_day_1, events_day_2):
                    self.assertEqual(len(events), 1)
                    self.assertEqual(events[0]["time"], start_time)
                    self.assertEqual(events[0]["session_end"], end_time)
                    self.assertIn("2", events[0]["duration"])
                self.assertEqual(len(get_objects(child=self.child)), 1)

                instance.delete()

    def test_tummy_time_notes_appear_in_timeline(self):
        """
        Notes on a Tummy Time entry should reach the timeline events, like the
        notes of the other care entry models do.
        """
        day = timezone.make_aware(datetime.datetime(2023, 1, 1))
        start = day.replace(hour=10, minute=0)
        end = day.replace(hour=10, minute=10)

        models.TummyTime.objects.create(
            child=self.child,
            start=start,
            end=end,
            milestone="Lifted head",
            notes="Seemed tired today",
        )

        events = get_objects(date=day, child=self.child)

        self.assertEqual(len(events), 1)
        for event in events:
            self.assertIn("Lifted head", event["details"])
            self.assertIn("Seemed tired today", event["details"])

    def test_medication_next_dose_spanning_midnight(self):
        """
        Medication doses with a next_dose_interval that wear off on the next day
        should show the start on Day 1 and the end ("wore off") on Day 2.
        """
        day_1 = timezone.make_aware(datetime.datetime(2023, 1, 1))
        day_2 = timezone.make_aware(datetime.datetime(2023, 1, 2))

        start_time = day_1.replace(hour=23, minute=0)
        interval = datetime.timedelta(hours=2)

        instance = models.Medication.objects.create(
            child=self.child,
            name="Tylenol",
            time=start_time,
            next_dose_interval=interval,
        )

        events_day_1 = get_objects(date=day_1, child=self.child)
        events_day_2 = get_objects(date=day_2, child=self.child)

        # Day 1: should contain the "start" event
        self.assertEqual(len(events_day_1), 1)
        self.assertEqual(events_day_1[0]["type"], "start")
        self.assertEqual(events_day_1[0]["time"], start_time)

        # Day 2: should contain the "end" event (wore off)
        self.assertEqual(len(events_day_2), 1)
        self.assertEqual(events_day_2[0]["type"], "end")
        self.assertEqual(events_day_2[0]["time"], start_time + interval)

        instance.delete()


class TimelineHistoryViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from zoneinfo import ZoneInfo

        cls.user = get_user_model().objects.create_user(
            "timeline-history", is_superuser=True
        )
        cls.user.settings.timezone = "Pacific/Honolulu"
        cls.user.settings.save()
        cls.child = models.Child.objects.create(
            first_name="Alice", last_name="Timeline", birth_date="2026-01-01"
        )
        cls.other = models.Child.objects.create(
            first_name="Ben", last_name="Timeline", birth_date="2026-01-01"
        )
        cls.day = datetime.datetime(2026, 9, 19, tzinfo=ZoneInfo("Pacific/Honolulu"))
        cls.old = models.Note.objects.create(
            child=cls.child,
            time=cls.day - datetime.timedelta(days=2),
            note="Older history marker",
        )
        cls.note = models.Note.objects.create(
            child=cls.child,
            time=cls.day
            + datetime.timedelta(hours=23, minutes=59, seconds=59, microseconds=500000),
            note="Selected day marker",
        )
        models.Temperature.objects.create(
            child=cls.child, time=cls.day, temperature=37, entry_unit="C"
        )
        models.Note.objects.create(
            child=cls.other, time=cls.day, note="Other child marker"
        )

    def setUp(self):
        self.addCleanup(timezone.deactivate)
        self.client.force_login(self.user)

    def test_all_dates_by_default_and_local_day_activity_filters(self):
        response = self.client.get("/timeline/", {"scope": self.child.slug})
        self.assertContains(response, "Older history marker")
        self.assertContains(response, "Selected day marker")
        self.assertNotContains(response, "Other child marker")
        self.assertIsNone(response.context["date"])
        times = [event["time"] for event in response.context["timeline_objects"]]
        self.assertEqual(times, sorted(times, reverse=True))
        response = self.client.get(
            "/timeline/", {"date": "2026-09-19", "activity": "note"}
        )
        self.assertContains(response, "Selected day marker")
        self.assertNotContains(response, "Older history marker")
        self.assertEqual(len(response.context["timeline_objects"]), 1)
        response = self.client.get("/timeline/", {"activity": "note"})
        self.assertContains(response, "Older history marker")
        self.assertEqual(
            {event["model_name"] for event in response.context["timeline_objects"]},
            {"note"},
        )

    def test_history_pagination_keeps_filters_and_child_pages_independent(self):
        for index in range(55):
            models.Note.objects.create(
                child=self.child,
                time=self.day + datetime.timedelta(minutes=index),
                note="History entry " + str(index),
            )
        response = self.client.get(
            "/timeline/",
            {
                "scope": "compare",
                "activity": "note",
                "page_child_" + str(self.child.pk): 2,
            },
        )
        panels = {
            panel["child"].pk: panel for panel in response.context["timeline_panels"]
        }
        self.assertEqual(panels[self.child.pk]["timeline_page"].number, 2)
        self.assertEqual(panels[self.other.pk]["timeline_page"].number, 1)
        self.assertEqual(len(panels[self.child.pk]["timeline_objects"]), 7)
        self.assertContains(response, "activity=note")
        self.assertContains(response, "Newer events")

    def test_invalid_filter_shows_error_instead_of_unfiltered_history(self):
        for params in ({"date": "invalid"}, {"activity": "unknown"}):
            response = self.client.get("/timeline/", params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["timeline_filter"].errors)
            self.assertNotContains(response, "Older history marker")

    def test_page_headings_replace_breadcrumb_navigation(self):
        from django.urls import reverse

        for path in (
            reverse("dashboard:dashboard"),
            reverse("dashboard:dashboard-child", args=[self.child.slug]),
            reverse("core:timeline"),
            reverse("reports:report-height-change-child", args=[self.child.slug]),
        ):
            response = self.client.get(path, {"scope": "all"})
            self.assertNotContains(response, 'aria-label="breadcrumb"')
            self.assertContains(response, "<h1>")
            self.assertNotContains(response, "Your household at a glance")

    def test_feeding_interval_uses_same_child_even_outside_selected_day(self):
        previous = self.day - datetime.timedelta(days=3)
        for child, start in (
            (self.child, previous),
            (self.other, self.day - datetime.timedelta(hours=1)),
            (self.child, self.day),
        ):
            models.Feeding.objects.create(
                child=child, start=start, end=start, type="formula", method="bottle"
            )
        events = get_objects(self.day, activity="feeding")
        self.assertEqual(len(events), 1)
        from django.utils.timesince import timesince

        self.assertEqual(
            events[0]["time_since_prev"], timesince(previous, now=self.day)
        )

    def test_activity_filter_cannot_expose_unpermitted_records(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user("timeline-restricted")
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="view_temperature"
            )
        )
        self.client.force_login(user)
        response = self.client.get("/timeline/")
        self.assertNotContains(response, "Older history marker")
        self.assertEqual(
            {event["model_name"] for event in response.context["timeline_objects"]},
            {"temperature"},
        )
        response = self.client.get("/timeline/", {"activity": "note"})
        self.assertTrue(response.context["timeline_filter"].errors)
        self.assertNotContains(response, "Older history marker")

    def test_calendar_periods_share_exact_boundaries_across_children(self):
        from zoneinfo import ZoneInfo

        cases = (
            ("week", "2026-01-01", "2025-12-28", "2026-01-03"),
            ("month", "2024-02-15", "2024-02-01", "2024-02-29"),
            ("year", "2024-09-19", "2024-01-01", "2024-12-31"),
        )
        for period, anchor, first, last in cases:
            with self.subTest(period=period):
                start = datetime.datetime.fromisoformat(first).replace(
                    tzinfo=ZoneInfo("Pacific/Honolulu")
                )
                end = datetime.datetime.fromisoformat(last).replace(
                    tzinfo=start.tzinfo,
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=999999,
                )
                for child in (self.child, self.other):
                    for suffix, moment in (
                        ("before", start - datetime.timedelta(microseconds=1)),
                        ("start", start),
                        ("end", end),
                        ("after", end + datetime.timedelta(microseconds=1)),
                    ):
                        models.Note.objects.create(
                            child=child,
                            time=moment,
                            note=period + " boundary " + suffix,
                        )
                response = self.client.get(
                    "/timeline/",
                    {
                        "scope": "compare",
                        "activity": "note",
                        "period": period,
                        "date": anchor,
                    },
                )
                self.assertEqual(response.context["range_start"].isoformat(), first)
                self.assertEqual(response.context["range_end"].isoformat(), last)
                self.assertContains(response, "Same period for every child")
                for panel in response.context["timeline_panels"]:
                    events = panel["timeline_objects"]
                    self.assertTrue(
                        all(start <= event["time"] <= end for event in events)
                    )
                    descriptions = " ".join(
                        detail for event in events for detail in event["details"]
                    )
                    self.assertIn(period + " boundary start", descriptions)
                    self.assertIn(period + " boundary end", descriptions)
                    self.assertNotIn(period + " boundary before", descriptions)
                    self.assertNotIn(period + " boundary after", descriptions)

    def test_period_navigation_preserves_comparison_and_activity_but_resets_pages(self):
        from urllib.parse import parse_qs, urlsplit

        response = self.client.get(
            "/timeline/",
            {
                "scope": "compare",
                "period": "month",
                "date": "2024-02-15",
                "activity": "note",
                "page_child_" + str(self.child.pk): 2,
            },
        )
        previous = parse_qs(urlsplit(response.context["previous_period_url"]).query)
        following = parse_qs(urlsplit(response.context["next_period_url"]).query)
        self.assertEqual(previous["date"], ["2024-01-31"])
        self.assertEqual(following["date"], ["2024-03-01"])
        self.assertEqual(following["scope"], ["compare"])
        self.assertEqual(following["activity"], ["note"])
        self.assertEqual(following["period"], ["month"])
        self.assertFalse(any(key.startswith("page") for key in following))
        next_page = self.client.get("/timeline/" + response.context["next_period_url"])
        self.assertEqual(str(next_page.context["range_end"]), "2024-03-31")

    def test_all_dates_and_invalid_period_edges(self):
        response = self.client.get(
            "/timeline/",
            {
                "period": "all",
                "date": "2026-09-19",
                "activity": "note",
                "scope": self.child.slug,
            },
        )
        self.assertIsNone(response.context["range_start"])
        self.assertContains(response, "Older history marker")
        for params in ({"period": "unknown"}, {"period": "week", "date": "0001-01-01"}):
            response = self.client.get("/timeline/", params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["timeline_filter"].errors)
        response = self.client.get("/timeline/", {"period": "year"})
        self.assertEqual(
            response.context["range_start"].year, timezone.localdate().year
        )

    def test_month_range_uses_local_midnight_across_daylight_saving(self):
        from zoneinfo import ZoneInfo

        self.user.settings.timezone = "America/New_York"
        self.user.settings.save()
        for marker, moment in (
            (
                "DST included",
                datetime.datetime(
                    2026, 3, 31, 23, 59, tzinfo=ZoneInfo("America/New_York")
                ),
            ),
            (
                "DST excluded",
                datetime.datetime(
                    2026, 4, 1, 0, 0, tzinfo=ZoneInfo("America/New_York")
                ),
            ),
        ):
            models.Note.objects.create(child=self.child, time=moment, note=marker)
        response = self.client.get(
            "/timeline/",
            {
                "period": "month",
                "date": "2026-03-15",
                "activity": "note",
                "scope": self.child.slug,
            },
        )
        self.assertContains(response, "DST included")
        self.assertNotContains(response, "DST excluded")


class TimelineSessionCardsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.user = get_user_model().objects.create_user(
            "session-timeline", is_superuser=True
        )
        cls.child = models.Child.objects.create(
            first_name="Avery", last_name="Example", birth_date="2023-01-01"
        )
        cls.other = models.Child.objects.create(
            first_name="Riley", last_name="Example", birth_date="2023-01-01"
        )
        cls.day = timezone.make_aware(datetime.datetime(2024, 1, 2))

    def test_long_session_matches_middle_day_without_truncation(self):
        entry = models.Sleep.objects.create(
            child=self.child,
            start=self.day - datetime.timedelta(hours=2),
            end=self.day + datetime.timedelta(days=1, hours=2),
        )
        events = get_objects(self.day, self.child, activity="sleep")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["time"], entry.start)
        self.assertEqual(events[0]["session_end"], entry.end)
        self.assertEqual(
            get_objects(
                self.day + datetime.timedelta(days=2), self.child, activity="sleep"
            ),
            [],
        )

    def test_all_saved_duration_activities_use_one_range(self):
        activity_type = models.ActivityType.objects.create(name="Reading")
        for model in (
            models.Sleep,
            models.Feeding,
            models.Pumping,
            models.TummyTime,
            models.BathTime,
            models.CustomActivity,
        ):
            with self.subTest(model=model.__name__):
                kwargs = dict(
                    start=self.day, end=self.day + datetime.timedelta(minutes=30)
                )
                if model is models.Pumping:
                    kwargs["amount"] = 60
                else:
                    kwargs["child"] = self.child
                if model is models.Feeding:
                    kwargs.update(type="formula", method="bottle")
                if model is models.CustomActivity:
                    kwargs["activity_type"] = activity_type
                entry = model.objects.create(**kwargs)
                events = get_objects(self.day, activity=entry.model_name)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["session_end"], entry.end)
                self.assertIn("30", events[0]["duration"])
                self.assertNotIn("in_progress", events[0])
                entry.delete()

    def test_durationless_feeding_is_not_in_progress(self):
        models.Feeding.objects.create(
            child=self.child,
            start=self.day,
            end=self.day,
            type="formula",
            method="bottle",
        )
        event = get_objects(self.day, self.child, activity="feeding")[0]
        self.assertIsNone(event["session_end"])
        self.assertNotIn("in_progress", event)
        self.assertEqual(
            get_objects(
                self.day + datetime.timedelta(days=1), self.child, activity="feeding"
            ),
            [],
        )

    def test_active_and_paused_timers_respect_permissions_and_child(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        now = timezone.now()
        current = models.Timer.objects.create(
            user=self.user,
            child=self.child,
            start=now - datetime.timedelta(minutes=45),
            context={"activity": "sleep"},
        )
        models.Timer.objects.create(
            user=self.user, child=self.other, start=now, context={"activity": "sleep"}
        )
        models.Timer.objects.create(
            user=self.user, start=now, context={"activity": "pumping"}
        )
        viewer = get_user_model().objects.create_user("restricted-session-viewer")
        viewer.settings.restrict_children = True
        viewer.settings.save()
        viewer.settings.allowed_children.add(self.child)
        viewer.user_permissions.add(
            Permission.objects.get(codename="view_timer"),
            Permission.objects.get(codename="view_sleep"),
        )
        events = get_objects(user=viewer)
        timers = [event for event in events if event.get("in_progress")]
        self.assertEqual(len(timers), 1)
        self.assertIn("Avery", str(timers[0]["event"]))
        self.assertFalse(timers[0]["paused"])
        current.paused_at = now - datetime.timedelta(minutes=10)
        current.paused_total = datetime.timedelta(minutes=5)
        current.save()
        events = get_objects(child=self.child, user=viewer, activity="sleep")
        self.assertTrue(events[0]["paused"])
        self.assertIn("30", events[0]["duration"])
        self.assertEqual(get_objects(user=viewer, activity="feeding"), [])
        self.client.force_login(viewer)
        response = self.client.get(
            "/timeline/", {"scope": self.child.slug, "activity": "sleep"}
        )
        self.assertContains(response, "Paused")
        self.assertNotContains(response, "Riley")

    def test_timer_replaced_by_saved_entry_and_not_shown_without_permission(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        timer = models.Timer.objects.create(
            user=self.user,
            child=self.child,
            start=self.day,
            context={"activity": "sleep"},
        )
        self.assertTrue(
            get_objects(self.day, self.child, self.user, "sleep")[0]["in_progress"]
        )
        viewer = get_user_model().objects.create_user("no-timer-permission")
        viewer.user_permissions.add(Permission.objects.get(codename="view_sleep"))
        self.assertEqual(get_objects(self.day, self.child, viewer, "sleep"), [])
        timer.delete()
        models.Sleep.objects.create(
            child=self.child,
            start=self.day,
            end=self.day + datetime.timedelta(minutes=30),
        )
        events = get_objects(self.day, self.child, self.user, "sleep")
        self.assertEqual(len(events), 1)
        self.assertNotIn("in_progress", events[0])

    def test_clock_change_keeps_actual_duration_and_offsets(self):
        from zoneinfo import ZoneInfo

        zone = ZoneInfo("America/New_York")
        start = datetime.datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=0)
        end = datetime.datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=1)
        models.Sleep.objects.create(child=self.child, start=start, end=end)
        with timezone.override(zone):
            event = get_objects(child=self.child, activity="sleep")[0]
            self.assertTrue(event["clock_change"])
            self.assertIsNotNone(event["session_end"])
            self.assertIn("1", event["duration"])

    def test_rendered_range_uses_preferred_clock_and_keeps_end_date(self):
        self.user.settings.timezone = "UTC"
        self.user.settings.time_format = "24"
        self.user.settings.save()
        models.Sleep.objects.create(
            child=self.child,
            start=self.day.replace(hour=23),
            end=self.day + datetime.timedelta(days=1, hours=1),
        )
        self.client.force_login(self.user)
        response = self.client.get(
            "/timeline/", {"scope": self.child.slug, "activity": "sleep"}
        )
        self.assertContains(response, 'class="timeline-event"', count=1)
        self.assertContains(response, 'datetime="2024-01-03T01:00:00+00:00"')
        self.assertContains(response, "23:00")
        self.assertContains(response, "01:00")
        self.assertNotContains(response, "woke up")
