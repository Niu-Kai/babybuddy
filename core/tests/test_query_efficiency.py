from datetime import date, datetime, timedelta, timezone as tz
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import models, timeline
from core.bmi import current_bmi
from reports import graphs


class QueryEfficiencyTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "query-review", is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Alice", birth_date=date(2024, 1, 1)
        )
        self.other = models.Child.objects.create(
            first_name="Ben", birth_date=date(2024, 1, 1)
        )

    def add_measurements(self, day):
        models.Weight.objects.create(
            child=self.child, date=day, weight=5, entry_unit="kg"
        )
        models.Height.objects.create(
            child=self.child, date=day, height=50, entry_unit="cm"
        )

    def test_bmi_sources_are_loaded_without_per_row_queries(self):
        self.add_measurements(date(2024, 1, 1))
        with self.assertNumQueries(1):
            entry = current_bmi(self.child)
            self.assertEqual(entry.bmi, 20)
            self.assertEqual(entry.source_weight.weight, 5)
            self.assertEqual(entry.source_height.height, 50)
        url = reverse("core:bmi-list")
        params = {"scope": self.child.slug}
        self.client.get(url, params)
        with CaptureQueriesContext(connection) as baseline:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        for day in range(2, 11):
            self.add_measurements(date(2024, 1, day))
        with CaptureQueriesContext(connection) as expanded:
            response = self.client.get(url, params)
        self.assertEqual(response.context["record_count"], 10)
        self.assertEqual(len(baseline), len(expanded))

    def test_growth_graphs_read_each_dataset_once(self):
        self.add_measurements(date(2024, 2, 1))
        models.HeadCircumference.objects.create(
            child=self.child,
            date=date(2024, 2, 1),
            head_circumference=35,
            entry_unit="cm",
        )
        for model, percentile_model, graph in (
            (models.Weight, models.WeightPercentile, graphs.weight_change),
            (models.Height, models.HeightPercentile, graphs.height_change),
            (
                models.HeadCircumference,
                models.HeadCircumferencePercentile,
                graphs.head_circumference_change,
            ),
        ):
            with self.subTest(model=model), patch(
                "plotly.offline.plot",
                return_value="<div><script>chart()</script></div>",
            ) as plot:
                with self.assertNumQueries(2):
                    graph(
                        model.objects.filter(child=self.child),
                        percentile_model.objects.filter(sex="girl"),
                        self.child.birth_date,
                    )
                figure = plot.call_args.args[0]
                self.assertEqual(len(figure.data), 6)
                self.assertEqual(list(figure.data[0].x), [date(2024, 2, 1)])
                for trace in figure.data:
                    self.assertEqual(len(trace.x), len(trace.y))

    def test_comparison_builds_one_chart_per_child(self):
        moment = datetime(2024, 1, 2, tzinfo=tz.utc)
        for child in (self.child, self.other):
            models.Feeding.objects.create(
                child=child, start=moment, end=moment, type="formula", method="bottle"
            )
        with patch(
            "reports.views.graphs.feeding_intervals", return_value=("chart", "script")
        ) as graph:
            response = self.client.get(
                reverse(
                    "reports:report-feeding-intervals-child", args=[self.child.slug]
                ),
                {"scope": "compare"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(graph.call_count, 2)
        self.assertEqual(
            [panel["object"].pk for panel in response.context["report_panels"]],
            [self.child.pk, self.other.pk],
        )
        self.assertEqual(
            {call.args[0][0].child_id for call in graph.call_args_list},
            {self.child.pk, self.other.pk},
        )

    def test_timeline_tags_and_foods_use_bounded_queries(self):
        tag = models.Tag.objects.create(name="Morning", color="#123456")
        moment = datetime(2024, 1, 2, tzinfo=tz.utc)
        for n in range(10):
            entry = models.Feeding.objects.create(
                child=self.child,
                start=moment + timedelta(hours=n),
                end=moment + timedelta(hours=n, minutes=10),
                type="solid food",
                method="parent fed",
            )
            entry.tags.add(tag)
            models.Food.objects.create(
                feeding=entry, child=self.child, time=entry.start, name=f"Food {n}"
            )
        # One query each for meals, tags, and linked foods, independent of row count.
        with self.assertNumQueries(3):
            events = timeline.get_objects(child=self.child, activity="feeding")
            tags = [[value.pk for value in event["tags"]] for event in events]
        self.assertEqual(len(events), 10)
        self.assertTrue(all(value == [tag.pk] for value in tags))
        self.assertTrue(
            all(
                any(detail.startswith("Food ") for detail in event["details"])
                for event in events
            )
        )
