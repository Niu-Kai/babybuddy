# -*- coding: utf-8 -*-
import datetime

from django.test import TestCase
from django.utils import timezone

from core import fields


class DateTimeFieldTestCase(TestCase):
    """Ambiguous wall times need a choice; nonexistent times must not be shifted."""

    def setUp(self):
        timezone.activate("America/New_York")

    def tearDown(self):
        timezone.deactivate()

    def test_normal_time(self):
        value = fields.DateTimeField().clean("2023-11-05T12:00:00")
        self.assertEqual(value.utcoffset(), datetime.timedelta(hours=-5))

    def test_ambiguous_time_requires_clarification(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            fields.DateTimeField().clean("2023-11-05T01:30:00")

    def test_non_existent_time_is_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            fields.DateTimeField().clean("2024-03-10T02:30:00")

    def test_invalid_still_rejected(self):
        with self.assertRaises(Exception):
            fields.DateTimeField().clean("not a date")


class FloatFieldTestCase(TestCase):
    """A comma decimal separator is accepted (#1000)."""

    def test_comma_decimal(self):
        self.assertEqual(fields.FloatField().clean("3,5"), 3.5)

    def test_period_decimal(self):
        self.assertEqual(fields.FloatField().clean("3.5"), 3.5)

    def test_thousands_with_period_untouched(self):
        # Ambiguous input is left to the normal validation.
        with self.assertRaises(Exception):
            fields.FloatField().clean("1,234.5")
