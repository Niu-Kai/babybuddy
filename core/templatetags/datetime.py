# -*- coding: utf-8 -*-
from django import template
from django.conf import settings
from django.template.defaultfilters import time as default_time_filter
from django.utils import timezone, formats
from django.utils.translation import gettext_lazy as _

from babybuddy import preferences

register = template.Library()


def _time_format():
    """The user's preferred time format, or the locale's TIME_FORMAT."""
    return preferences.get_time_format() or "TIME_FORMAT"


@register.filter(name="time", expects_localtime=True)
def time_filter(value, arg=None):
    """
    Django's `time` filter, honouring the user's 24-hour clock preference
    (#679) when no explicit format is given.
    """
    if arg is None and preferences.get_time_format():
        arg = preferences.get_time_format()
    return default_time_filter(value, arg)


@register.filter()
def datetime_short(date):
    """
    Format a datetime object as short string for list views
    :param date: datetime instance
    :return: a string representation of `date`.
    """
    date_string = None
    time_string = None

    # The value received from templates will be UTC so it must be converted to
    # localtime here.
    date = timezone.localtime(date)

    now = timezone.localtime()
    if now.date() == date.date():
        date_string = _("Today")
        time_string = formats.date_format(date, format=_time_format())
    elif (
        now.year == date.year
        and formats.get_format("SHORT_MONTH_DAY_FORMAT") != "SHORT_MONTH_DAY_FORMAT"
    ):
        # Use the custom `SHORT_MONTH_DAY_FORMAT` format if available for the
        # current locale.
        date_string = formats.date_format(date, format="SHORT_MONTH_DAY_FORMAT")
        time_string = formats.date_format(date, format=_time_format())

    if not date_string and preferences.get_time_format():
        date_string = formats.date_format(date, format="SHORT_DATE_FORMAT")
        time_string = formats.date_format(date, format=_time_format())
    if not date_string:
        date_string = formats.date_format(date, format="SHORT_DATETIME_FORMAT")

    if date_string and time_string:
        datetime_string = "{}, {}".format(date_string, time_string)
    else:
        datetime_string = date_string

    return datetime_string
