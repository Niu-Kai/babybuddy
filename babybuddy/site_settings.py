# -*- coding: utf-8 -*-
from datetime import time

from django.utils.translation import gettext_lazy as _

import dbsettings

from django.forms.fields import BooleanField, FloatField, TimeField
from core.fields import NapStartMaxTimeField, NapStartMinTimeField
from .widgets import TimeInput
from django.forms.widgets import CheckboxInput


class NapStartMaxTimeValue(dbsettings.TimeValue):
    field = NapStartMaxTimeField


class NapStartMinTimeValue(dbsettings.TimeValue):
    field = NapStartMinTimeField


class NapSettings(dbsettings.Group):
    nap_start_min = NapStartMinTimeValue(
        default=time(6),
        description=_("Default minimum nap start time"),
        help_text=_(
            "The minimum default time that a sleep entry is consider a nap. If set the nap property will be preselected if the start time is within the bounds."
        ),
        widget=TimeInput,
    )
    nap_start_max = NapStartMaxTimeValue(
        default=time(18),
        description=_("Default maximum nap start time"),
        help_text=_(
            "The maximum default time that a sleep entry is consider a nap. If set the nap property will be preselected if the start time is within the bounds."
        ),
        widget=TimeInput,
    )


class DayStartValue(dbsettings.TimeValue):
    field = TimeField


class DashboardSettings(dbsettings.Group):
    day_start = DayStartValue(
        default=time(0),
        description=_("Start of the day"),
        help_text=_(
            "Dashboard daily totals count entries before this time towards the "
            "previous day. Set e.g. 03:00 so a late-night feed belongs to the "
            "day before."
        ),
        widget=TimeInput,
    )


class DiaperChangeDefaultAmountValue(dbsettings.FloatValue):
    field = FloatField


class DiaperChangeSettings(dbsettings.Group):
    default_amount = DiaperChangeDefaultAmountValue(
        default=0,
        description=_("Default diaper change amount"),
        help_text=_(
            "Pre-filled amount for a new diaper change. 0 leaves the field empty."
        ),
    )


class WebhookSettings(dbsettings.Group):
    url = dbsettings.StringValue(
        required=False,
        default="",
        description=_("Webhook URL"),
        help_text=_(
            "Baby Buddy sends a JSON POST here whenever an entry is added, "
            "changed or deleted, e.g. a Home Assistant webhook trigger URL. "
            "Leave empty to disable."
        ),
    )
    secret = dbsettings.StringValue(
        required=False,
        default="",
        description=_("Webhook secret"),
        help_text=_(
            "Optional. Requests then carry an X-BabyBuddy-Signature header: the "
            "HMAC-SHA256 of the body with this secret."
        ),
    )


class FeedingDiffEndValue(dbsettings.BooleanValue):
    field = BooleanField


class FeedingSettings(dbsettings.Group):
    feeding_diff_end = FeedingDiffEndValue(
        required=False,
        default=False,
        description=_("Time diff between feedings based on end"),
        help_text=_(
            "Use feeding end instead of start time for displaying time between feedings"
        ),
        widget=CheckboxInput,
    )
