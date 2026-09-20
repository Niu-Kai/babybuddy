# -*- coding: utf-8 -*-
import datetime as dt
import json

from django.test import TestCase
from django.utils import timezone

from core import models
from reports import utils
from reports.graphs import pumping_amounts


def _layout(js):
    """Extract the Plotly layout object from a graph's script output."""
    decoder = json.JSONDecoder()
    position = js.index("Plotly.newPlot(")
    position = js.index(",", position) + 1  # skip the element id
    _, position = decoder.raw_decode(js, js.index("[", position))  # data
    layout, _ = decoder.raw_decode(js, js.index("{", position))
    return layout


class PumpingAmountsTestCase(TestCase):
    def setUp(self):
        self.original_tz = timezone.get_current_timezone()
        self.tz = dt.timezone(dt.timedelta(days=-1, hours=1))
        timezone.activate(self.tz)

    def tearDown(self):
        timezone.activate(self.original_tz)

    def test_pumping_amounts(self):
        c = models.Child(birth_date=dt.datetime.now())
        c.save()

        models.Pumping.objects.create(
            child=c,
            start=dt.datetime(2000, 1, 1, 0, 0, tzinfo=dt.timezone.utc),
            end=dt.datetime(2000, 1, 1, 0, 15, tzinfo=dt.timezone.utc),
            amount=50.0,
        )

        html, js = pumping_amounts(models.Pumping.objects.filter(child=c))
        self.assertIsNotNone(html)
        self.assertIsNotNone(js)

    def test_range_bound_to_data(self):
        """
        The x axis range must be pinned to the recorded dates so Plotly cannot
        extend the axis into the future (issues #706 and #860).
        """
        c = models.Child(birth_date=dt.datetime.now())
        c.save()
        now = timezone.localtime()
        for day in range(3):
            start = now - dt.timedelta(days=day, hours=6)
            models.Pumping.objects.create(
                child=c, start=start, end=start + dt.timedelta(minutes=15), amount=60
            )

        html, js = pumping_amounts(models.Pumping.objects.filter(child=c))
        xaxis = _layout(js)["xaxis"]
        self.assertEqual(xaxis["type"], "date")
        self.assertTrue(xaxis["autorange"])
        expected = utils.autorangeoptions(
            [timezone.localtime(p.start).date() for p in models.Pumping.objects.all()]
        )
        self.assertEqual(xaxis["autorangeoptions"], expected)

    def test_totals_are_rounded(self):
        """Daily totals are float sums; labels must not show binary noise."""
        c = models.Child(birth_date=dt.datetime.now())
        c.save()
        now = timezone.localtime()
        for amount in (0.1, 0.2):
            models.Pumping.objects.create(
                child=c,
                start=now - dt.timedelta(hours=1),
                end=now - dt.timedelta(minutes=45),
                amount=amount,
            )

        html, js = pumping_amounts(models.Pumping.objects.filter(child=c))
        annotations = _layout(js)["annotations"]
        self.assertEqual([a["text"] for a in annotations], ["0.3"])
