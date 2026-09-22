from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as django_timezone
from core import models
from reports import graphs
from reports.growth import growth_chart, bmi_medians


class ReportRedesignTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "report-redesign", is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Alice", birth_date=date(2024, 1, 1)
        )
        self.day = date(2024, 1, 22)
        self.moment = datetime(2024, 1, 22, 12, tzinfo=timezone.utc)

    def chart(self, function, *args, **kwargs):
        with django_timezone.override("UTC"), patch(
            "plotly.offline.plot", return_value="<div><script>plot()</script></div>"
        ) as plot:
            function(*args, **kwargs)
        return plot.call_args.args[0]

    def test_fahrenheit_preference_and_override_convert_values_and_axes(self):
        models.Temperature.objects.create(
            child=self.child, time=self.moment, temperature=37, entry_unit="C"
        )
        self.user.settings.temperature_unit = "F"
        self.user.settings.save()
        url = reverse("reports:report-temperature-change-child", args=[self.child.slug])
        for query, expected, label in [
            ({}, 98.6, "°F"),
            ({"unit": "C"}, 37, "°C"),
            ({"unit": "invalid"}, 98.6, "°F"),
        ]:
            with self.subTest(query=query), patch(
                "plotly.offline.plot", return_value="<div><script>plot()</script></div>"
            ) as plot:
                response = self.client.get(url, {"scope": self.child.slug, **query})
                figure = plot.call_args.args[0]
                self.assertEqual(list(figure.data[0].y), [expected])
                self.assertIn(label, figure.layout.yaxis.title.text)
                self.assertContains(response, 'name="unit"')
                self.assertContains(response, 'class="report-chart-card"')
        models.Temperature.objects.create(
            child=self.child, time=self.moment + timedelta(hours=1), temperature=200
        )
        response = self.client.get(url, {"scope": self.child.slug})
        self.assertEqual(response.context["unknown_unit_count"], 1)
        self.assertContains(response, "no recorded unit")

    def test_diaper_report_counts_records_and_type_stacks_do_not_double_count(self):
        for amount, wet, solid in [
            (45.8, True, False),
            (0.2, True, True),
            (None, False, True),
        ]:
            models.DiaperChange.objects.create(
                child=self.child, time=self.moment, wet=wet, solid=solid, amount=amount
            )
        objects = models.DiaperChange.objects.all()
        figure = self.chart(graphs.diaperchange_amounts, objects)
        self.assertEqual(list(figure.data[0].y), [3])
        self.assertEqual(figure.layout.yaxis.dtick, 1)
        figure = self.chart(graphs.diaperchange_types, objects)
        self.assertEqual(sum(trace.y[0] for trace in figure.data), 3)
        url = reverse(
            "reports:report-diaperchange-amounts-child", args=[self.child.slug]
        )
        self.assertContains(self.client.get(url), "Diaper Changes per Day")

    def test_growth_references_are_age_matched_unit_converted_and_independent(self):
        models.Weight.objects.create(
            child=self.child, date=self.day, weight=4, entry_unit="kg"
        )
        objects = models.Weight.objects.all()
        figure = self.chart(growth_chart, objects, self.child, "weight", "lb", ["girl"])
        self.assertEqual(list(figure.data[0].x), [3])
        self.assertEqual(list(figure.data[0].y), [8.82])
        self.assertEqual(figure.data[0].mode, "lines+markers")
        self.assertFalse(figure.data[0].fill)
        self.assertFalse(figure.data[1].visible)
        self.assertTrue(figure.data[2].visible)
        for sex, trace in zip(("boy", "girl"), figure.data[1:]):
            self.assertEqual(trace.meta["reference"], sex)
            row = models.WeightPercentile.objects.get(
                sex=sex, age_in_days=timedelta(days=21)
            )
            index = list(trace.x).index(3)
            self.assertAlmostEqual(
                trace.y[index], round(row.p50_weight / 0.45359237, 2)
            )
        self.assertEqual(figure.layout.xaxis.type, "linear")
        self.assertIn("lbs", figure.layout.yaxis.title.text)

    def test_bmi_reference_source_and_no_extrapolation(self):
        self.assertAlmostEqual(bmi_medians()["boy"][0][1], 13.4069)
        self.assertAlmostEqual(bmi_medians()["girl"][0][1], 13.3363)
        models.Weight.objects.create(
            child=self.child, date=self.day, weight=4, entry_unit="kg"
        )
        models.Height.objects.create(
            child=self.child, date=self.day, height=50, entry_unit="cm"
        )
        figure = self.chart(
            growth_chart,
            models.BMI.objects.all(),
            self.child,
            "bmi",
            "",
            ["boy", "girl"],
        )
        self.assertEqual(figure.data[0].y[0], 16)
        self.assertEqual(len(figure.data), 3)
        self.child.birth_date = date(2010, 1, 1)
        figure = self.chart(
            growth_chart,
            models.BMI.objects.all(),
            self.child,
            "bmi",
            "",
            ["boy", "girl"],
        )
        self.assertEqual(len(figure.data), 1)

    def test_growth_tabs_keep_filters_and_obey_metric_permissions(self):
        url = reverse("reports:growth", args=[self.child.slug])
        response = self.client.get(
            url,
            {
                "metric": "height",
                "scope": "compare",
                "period": "month",
                "date": "2024-01-01",
                "reference_controls": "1",
                "reference": "girl",
            },
        )
        self.assertContains(response, "growth-tabs")
        self.assertEqual(response.context["growth_references"], ["girl"])
        self.assertEqual(response.context["growth_metric"], "height")
        self.assertContains(response, "period=month&amp;date=2024-01-01")
        restricted = get_user_model().objects.create_user("growth-restricted")
        restricted.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=["view_child", "view_height"],
            )
        )
        self.client.force_login(restricted)
        self.assertEqual(self.client.get(url, {"metric": "height"}).status_code, 200)
        self.assertEqual(self.client.get(url, {"metric": "weight"}).status_code, 403)

    def test_liquid_reports_convert_and_include_mixed_feedings(self):
        models.Feeding.objects.create(
            child=self.child,
            start=self.moment,
            end=self.moment,
            type="breast milk",
            method="bottle",
            amount=29.5735295625,
            secondary_type="formula",
            secondary_amount=29.5735295625,
            entry_unit="mL",
        )
        figure = self.chart(
            graphs.feeding_amounts, models.Feeding.objects.all(), unit="fl oz"
        )
        self.assertEqual([list(trace.y) for trace in figure.data], [[1], [1]])
        self.assertEqual(figure.layout.barmode, "stack")
        models.Pumping.objects.create(
            child=self.child,
            start=self.moment,
            end=self.moment,
            amount=59.147059125,
            entry_unit="mL",
        )
        figure = self.chart(
            graphs.pumping_amounts, models.Pumping.objects.all(), unit="fl oz"
        )
        self.assertEqual(list(figure.data[0].y), [2])

    def test_reports_home_has_no_duplicate_sex_links_or_intro(self):
        response = self.client.get(reverse("reports:home"))
        self.assertNotContains(response, "Explore growth")
        self.assertNotContains(response, "WHO Weight Percentiles")
        self.assertNotContains(response, "WHO Height Percentiles")

    def test_growth_labels_are_plain_text_without_encoding_artifacts(self):
        models.Weight.objects.create(
            child=self.child, date=self.day, weight=4, entry_unit="kg"
        )
        figure = self.chart(
            growth_chart,
            models.Weight.objects.all(),
            self.child,
            "weight",
            "kg",
            ["boy", "girl"],
        )
        self.assertEqual(
            [trace.name for trace in figure.data[1:]],
            ["Boys - WHO median", "Girls - WHO median"],
        )
        self.assertNotIn("\u00c2", figure.to_json())

    def test_sleep_blocks_have_outlines_and_neutral_unrecorded_time(self):
        start = datetime(2024, 1, 21, 23, tzinfo=timezone.utc)
        models.Sleep.objects.create(
            child=self.child, start=start, end=start + timedelta(hours=26), nap=False
        )
        figure = self.chart(
            graphs.sleep_pattern,
            models.Sleep.objects.all(),
            first_day=date(2024, 1, 22),
            last_day=date(2024, 1, 23),
            use_24_hour=True,
        )
        self.assertEqual(figure.layout.barmode, "overlay")
        self.assertEqual(figure.data[0].name, "No sleep recorded")
        self.assertEqual(list(figure.data[1].base), [0, 0])
        self.assertEqual(list(figure.data[1].y), [1440, 60])
        self.assertGreater(figure.data[1].marker.line.width, 0)
        self.assertIn("03:00", figure.layout.yaxis.ticktext)
        self.assertEqual(figure.layout.yaxis.range, (1440, 0))

    def test_sleep_filter_includes_sleep_that_started_before_selected_day(self):
        start = datetime(2024, 1, 21, 23, tzinfo=timezone.utc)
        models.Sleep.objects.create(
            child=self.child, start=start, end=start + timedelta(hours=3), nap=False
        )
        url = reverse("reports:report-sleep-pattern-child", args=[self.child.slug])
        with patch(
            "plotly.offline.plot", return_value="<div><script>plot()</script></div>"
        ) as plot:
            response = self.client.get(
                url, {"scope": self.child.slug, "period": "day", "date": "2024-01-22"}
            )
            self.assertEqual(response.status_code, 200)
            figure = plot.call_args.args[0]
            self.assertEqual(list(figure.data[1].y), [120])
            self.assertEqual(list(figure.data[1].base), [0])
        self.assertContains(response, "report-chart-card")

    def test_diaper_intervals_have_one_series_with_type_details(self):
        for hours, wet, solid in [(0, True, False), (2, False, True), (5, True, True)]:
            models.DiaperChange.objects.create(
                child=self.child,
                time=self.moment + timedelta(hours=hours),
                wet=wet,
                solid=solid,
            )
        figure = self.chart(
            graphs.diaperchange_intervals, models.DiaperChange.objects.all()
        )
        self.assertEqual(len(figure.data), 1)
        self.assertEqual(list(figure.data[0].y), [2, 3])
        self.assertIn("Solid", figure.data[0].customdata[0])
        self.assertIn("Wet + solid", figure.data[0].customdata[1])
        self.assertNotEqual(figure.data[0].name, "Total")

    def test_large_count_axes_and_histogram_remain_readable(self):
        from reports import utils

        for maximum in (3, 8, 60, 400, 3000):
            axis = utils.count_axis(maximum)
            self.assertGreaterEqual(axis["dtick"], 1)
            self.assertLessEqual(maximum / axis["dtick"], 6)
        models.DiaperChange.objects.bulk_create(
            [
                models.DiaperChange(
                    child=self.child,
                    time=self.moment + timedelta(hours=index),
                    wet=True,
                    solid=False,
                )
                for index in range(301)
            ]
        )
        figure = self.chart(
            graphs.diaperchange_lifetimes, models.DiaperChange.objects.all()
        )
        self.assertEqual(sum(figure.data[0].y), 300)
        self.assertGreater(figure.layout.yaxis.dtick, 1)
        self.assertGreater(figure.layout.template.data.bar[0].marker.line.width, 0)

    def test_daily_activity_preserves_overlapping_lanes_and_midnight(self):
        start = self.moment.replace(hour=23)
        end = start + timedelta(hours=3)
        intervals = [
            ("sleep", start, end, "Sleep"),
            (
                "feeding",
                start + timedelta(minutes=30),
                start + timedelta(minutes=45),
                "Feeding",
            ),
        ]
        figure = self.chart(
            graphs.activity_pattern,
            intervals,
            [],
            start.date(),
            end.date(),
            {"sleep": "Sleep", "feeding": "Feeding"},
        )
        sleep, feeding = figure.data
        self.assertEqual(list(sleep.y), [60, 120])
        self.assertEqual(list(feeding.y), [15])
        self.assertNotEqual(sleep.x[0], feeding.x[0])
        self.assertGreater(sleep.marker.line.width, 0)
        self.assertEqual(figure.layout.barmode, "overlay")
        self.assertLessEqual(len(figure.layout.yaxis.tickvals), 9)

    def test_sleep_daily_labels_totals_and_overlaps(self):
        start = self.moment.replace(hour=23)
        for offset, hours, nap in [(0, 3, False), (2, 2, True)]:
            models.Sleep.objects.create(
                child=self.child,
                start=start + timedelta(hours=offset),
                end=start + timedelta(hours=offset + hours),
                nap=nap,
            )
        figure = self.chart(
            graphs.sleep_pattern,
            models.Sleep.objects.all(),
            first_day=self.day,
            last_day=self.day + timedelta(days=2),
        )
        self.assertEqual(figure.layout.xaxis.type, "category")
        self.assertEqual(len(figure.layout.xaxis.tickvals), 3)
        self.assertIn("1h 00m", figure.layout.xaxis.ticktext[0])
        self.assertIn("3h 00m", figure.layout.xaxis.ticktext[1])
        self.assertIn("No entries", figure.layout.xaxis.ticktext[2])
        self.assertEqual(figure.layout.xaxis.tickangle, 0)

    def test_sleep_single_day_stays_narrow_and_labels_date_once(self):
        models.Sleep.objects.create(
            child=self.child,
            start=self.moment,
            end=self.moment + timedelta(hours=2),
        )
        figure = self.chart(
            graphs.sleep_pattern,
            models.Sleep.objects.all(),
            first_day=self.day,
            last_day=self.day,
        )
        self.assertEqual(list(figure.layout.xaxis.tickvals), [self.day.isoformat()])
        self.assertLess(figure.data[1].width, 0.5)
        html, _ = graphs.sleep_pattern(models.Sleep.objects.all())
        self.assertIn("max-width:360px", html)
        self.assertIn("sleep-comparison-scroll", html)

    def test_feeding_pattern_midnight_and_missing_duration(self):
        start = self.moment.replace(hour=23, minute=30)
        models.Feeding.objects.create(
            child=self.child,
            start=start,
            end=start + timedelta(hours=1),
            method="bottle",
            type="formula",
        )
        models.Feeding.objects.create(
            child=self.child,
            start=start + timedelta(hours=3),
            end=start + timedelta(hours=3),
            method="left breast",
            type="breast milk",
        )
        figure = self.chart(
            graphs.feeding_pattern,
            models.Feeding.objects.all(),
            first_day=self.day,
            last_day=self.day + timedelta(days=2),
            use_24_hour=True,
        )
        bars = [trace for trace in figure.data if trace.type == "bar"]
        points = [trace for trace in figure.data if trace.type == "scatter"]
        self.assertEqual(list(bars[0].y), [30, 30])
        self.assertEqual(list(bars[0].base), [1410, 0])
        self.assertEqual(len(points[0].x), 1)
        self.assertIn("Duration not recorded", points[0].hovertext[0])
        self.assertIn("1 feeding", figure.layout.xaxis.ticktext[0])
        self.assertIn("1 feeding", figure.layout.xaxis.ticktext[1])
        self.assertIn("0 feedings", figure.layout.xaxis.ticktext[2])
        self.assertIn("03:00", figure.layout.yaxis.ticktext)
        self.assertEqual(figure.layout.xaxis.tickvals, (0, 1, 2))
        self.assertEqual(figure.layout.xaxis.type, "linear")

    def test_feeding_pattern_day_filter_preserves_overnight_session(self):
        start = self.moment.replace(hour=23, minute=30)
        models.Feeding.objects.create(
            child=self.child,
            start=start,
            end=start + timedelta(hours=1),
            method="bottle",
            type="formula",
        )
        with patch(
            "plotly.offline.plot", return_value="<div><script>plot()</script></div>"
        ) as plot:
            response = self.client.get(
                reverse("reports:report-feeding-pattern-child", args=[self.child.slug]),
                {"scope": self.child.slug, "period": "day", "date": "2024-01-23"},
            )
            self.assertEqual(response.status_code, 200)
            figure = plot.call_args.args[0]
            self.assertEqual(list(figure.data[0].y), [30])
            self.assertIn("0 feedings", figure.layout.xaxis.ticktext[0])

    def test_activity_grid_has_one_label_per_day_and_instant_markers(self):
        figure = self.chart(
            graphs.activity_pattern,
            [("feeding", self.moment, self.moment, "Feeding")],
            [],
            self.day,
            self.day + timedelta(days=2),
            {"feeding": "Feeding"},
            use_24_hour=True,
        )
        self.assertEqual(figure.data[0].type, "scatter")
        self.assertEqual(len(figure.layout.xaxis.tickvals), 3)
        self.assertEqual(figure.layout.xaxis.tickangle, 0)
        self.assertEqual(len(figure.layout.shapes), 3)
        self.assertIn("03:00", figure.layout.yaxis.ticktext)

    def test_feeding_blocks_only_share_width_for_overlapping_sessions(self):
        for offset, method in [(0, "bottle"), (10, "left breast"), (120, "bottle")]:
            start = self.moment + timedelta(minutes=offset)
            models.Feeding.objects.create(
                child=self.child,
                start=start,
                end=start + timedelta(minutes=20),
                method=method,
                type="breast milk",
            )
        figure = self.chart(graphs.feeding_pattern, models.Feeding.objects.all())
        bottle, breast = figure.data
        self.assertNotEqual(bottle.x[0], breast.x[0])
        self.assertAlmostEqual(bottle.width[0], breast.width[0])
        self.assertGreater(bottle.width[1], bottle.width[0])
        self.assertGreater(bottle.width[1], 0.6)
        self.assertIn("20m", figure.layout.annotations[0].text)
        self.assertGreaterEqual(figure.layout.xaxis.tickfont.size, 15)
