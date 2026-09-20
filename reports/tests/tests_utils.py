# -*- coding: utf-8 -*-
import datetime

from django.test import TestCase

from reports import utils


class UtilsTestCase(TestCase):
    def test_autorangeoptions_accepts_any_order(self):
        dates = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 10)]
        ascending = utils.autorangeoptions(dates)
        descending = utils.autorangeoptions(list(reversed(dates)))
        strings = utils.autorangeoptions(["2024-01-10", "2024-01-01"])
        self.assertEqual(ascending, descending)
        self.assertEqual(ascending, strings)
        self.assertLess(ascending["minallowed"], ascending["maxallowed"])
