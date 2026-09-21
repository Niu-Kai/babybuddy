from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from core.models import Child, Height, Feeding, Sleep
from reports.views import report_entries
from reports import utils


class ReportFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "report-filters", is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = Child.objects.create(first_name="Alice", birth_date="2019-01-01")
        self.other = Child.objects.create(first_name="Ben", birth_date="2019-01-01")

    def entries(self, model, query):
        request = RequestFactory().get("/", query)
        request.user = self.user
        return report_entries(model, request, child=self.child)

    def test_periods_filter_date_only_and_local_time_entries(self):
        for day in (
            "2024-01-31",
            "2024-02-01",
            "2024-02-29",
            "2024-03-01",
            "2023-02-01",
        ):
            Height.objects.create(
                child=self.child, date=day, height=50, entry_unit="cm"
            )
        for period, expected in (
            ("day", 1),
            ("week", 2),
            ("month", 2),
            ("year", 4),
            ("all", 5),
        ):
            with self.subTest(period=period):
                self.assertEqual(
                    self.entries(
                        Height, {"period": period, "date": "2024-02-01"}
                    ).count(),
                    expected,
                )
        self.assertFalse(
            self.entries(Height, {"period": "month", "date": "invalid"}).exists()
        )
        self.assertEqual(
            self.entries(Height, {"from": "2024-02-01", "to": "2024-02-29"}).count(), 2
        )
        for hour in (9, 10):
            moment = datetime(2024, 2, 1, hour, tzinfo=dt_timezone.utc)
            Feeding.objects.create(
                child=self.child,
                start=moment,
                end=moment,
                type="formula",
                method="bottle",
            )
        with timezone.override(ZoneInfo("Pacific/Honolulu")):
            entries = self.entries(Feeding, {"period": "day", "date": "2024-02-01"})
            self.assertEqual(list(entries.values_list("start__hour", flat=True)), [0])

    def test_comparison_filters_empty_panels_and_percentile_links(self):
        Height.objects.create(
            child=self.child, date="2024-02-01", height=50, entry_unit="cm"
        )
        Height.objects.create(
            child=self.other, date="2024-01-01", height=60, entry_unit="cm"
        )
        url = reverse("reports:report-height-change-child", args=[self.child.slug])
        response = self.client.get(
            url, {"scope": "compare", "period": "month", "date": "2024-02-01"}
        )
        self.assertEqual(response.status_code, 200)
        panels = response.context["report_panels"]
        self.assertIn("html", panels[0])
        self.assertNotIn("html", panels[1])
        self.assertContains(response, 'class="plotly-graph-div"', count=1)
        self.assertContains(response, "There is not enough data", count=1)
        self.assertContains(response, "data-timeline-filters", count=1)
        self.assertContains(response, "period=month&amp;date=2024-02-01")
        self.assertContains(response, "Clear filters")
        self.assertEqual(response.context["report_range_end"], date(2024, 2, 29))
        response = self.client.get(
            url, {"scope": "compare", "period": "year", "date": "invalid"}
        )
        self.assertTrue(response.context["report_period"].errors)
        self.assertNotContains(response, 'class="plotly-graph-div"')

    def test_daily_activity_period_includes_overlapping_sleep_and_older_history(self):
        start = datetime(2024, 1, 31, 23, tzinfo=dt_timezone.utc)
        end = datetime(2024, 2, 1, 1, tzinfo=dt_timezone.utc)
        Sleep.objects.create(child=self.child, start=start, end=end)
        Sleep.objects.create(
            child=self.child,
            start=datetime(2023, 1, 1, tzinfo=dt_timezone.utc),
            end=datetime(2023, 1, 1, 1, tzinfo=dt_timezone.utc),
        )
        url = reverse("reports:report-activity-pattern-child", args=[self.child.slug])
        with patch(
            "reports.views.graphs.activity_pattern", return_value=("chart", "script")
        ) as graph:
            self.client.get(
                url, {"scope": self.child.slug, "period": "month", "date": "2024-02-01"}
            )
            intervals, _, first, last, _ = graph.call_args.args
            self.assertEqual(len(intervals), 1)
            self.assertEqual((first, last), (date(2024, 2, 1), date(2024, 2, 29)))
            self.client.get(url, {"scope": self.child.slug})
            self.assertEqual(len(graph.call_args.args[0]), 2)

    def test_feeding_has_only_one_add_button(self):
        response = self.client.get(reverse("core:feeding-list"))
        self.assertContains(response, "Add Feeding")
        self.assertNotContains(response, "Add Bottle Feeding")


class ChartMarkupTests(TestCase):
    def test_plotly_wrapper_is_complete_and_default_height_is_defined(self):
        import plotly.graph_objects as go
        import plotly.offline as plotly

        output = plotly.plot(
            go.Figure(
                data=[go.Scatter(x=[1, 2], y=[2, 3])],
                layout=utils.default_graph_layout_options(),
            ),
            output_type="div",
            include_plotlyjs=False,
        )
        html, script = utils.split_graph_output(output)
        self.assertEqual(html.count("<div"), html.count("</div>"))
        self.assertNotIn("<script", html)
        self.assertTrue(script.rstrip().endswith("</script>"))
        self.assertNotIn("</div>", script)
        self.assertIn("height:480px", html)
