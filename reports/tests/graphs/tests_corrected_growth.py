"""Upstream corrected-age regressions applied to our consolidated growth reports."""

import datetime as dt
from unittest.mock import patch

from django.test import TestCase

from core import models
from reports.growth import growth_chart


class CorrectedGrowthTests(TestCase):
    def chart(self, metric, due_date, measurement_date, references=("boy",)):
        child = models.Child.objects.create(
            first_name=f"Growth{models.Child.objects.count()}",
            last_name="Comparison",
            birth_date=dt.date(2025, 6, 1),
            due_date=due_date,
        )
        model, value, unit = {
            "weight": (models.Weight, 3, "kg"),
            "height": (models.Height, 50, "cm"),
        }[metric]
        record = model.objects.create(
            child=child,
            date=measurement_date,
            **{metric: value},
        )
        with patch("reports.growth.plotly.plot", return_value="<div></div>") as render:
            growth_chart(
                model.objects.filter(pk=record.pk), child, metric, unit, references
            )
        return render.call_args.args[0]

    def test_due_date_anchors_age_and_hover_preserves_actual_date(self):
        for metric in ("weight", "height"):
            with self.subTest(metric=metric):
                figure = self.chart(metric, dt.date(2025, 6, 24), dt.date(2025, 7, 1))
                self.assertEqual(list(figure.data[0].x), [1])
                self.assertEqual(list(figure.data[0].customdata[0]), ["2025-07-01", 7])
                self.assertIn("Corrected age", figure.layout.xaxis.title.text)
                self.assertIn("Corrected age", figure.data[0].hovertemplate)
                self.assertEqual(figure.data[1].x[0], 0)

    def test_absent_or_earlier_due_date_keeps_birth_age(self):
        for metric in ("weight", "height"):
            for due_date in (None, dt.date(2025, 5, 28), dt.date(2025, 6, 1)):
                with self.subTest(metric=metric, due_date=due_date):
                    figure = self.chart(metric, due_date, dt.date(2025, 6, 8))
                    self.assertEqual(list(figure.data[0].x), [1])
                    self.assertNotIn("Corrected", figure.layout.xaxis.title.text)
                    self.assertNotIn("Corrected", figure.data[0].hovertemplate)

    def test_early_measurements_do_not_extrapolate_reference_below_zero(self):
        for metric in ("weight", "height"):
            with self.subTest(metric=metric):
                figure = self.chart(metric, dt.date(2025, 6, 24), dt.date(2025, 6, 10))
                self.assertEqual(list(figure.data[0].x), [-2])
                self.assertEqual(figure.data[0].customdata[0][0], "2025-06-10")
                for reference in figure.data[1:]:
                    self.assertTrue(all(age >= 0 for age in reference.x))

    def test_hidden_references_keep_explicit_corrected_axis(self):
        # Our redesigned chart uses age on the x axis, unlike upstream's date axis.
        # Corrected age remains truthful even when the reference lines are hidden.
        figure = self.chart("weight", dt.date(2025, 6, 24), dt.date(2025, 7, 1), ())
        self.assertIn("Corrected age", figure.layout.xaxis.title.text)
        self.assertEqual(list(figure.data[0].x), [1])
        self.assertTrue(all(trace.visible is False for trace in figure.data[1:]))
