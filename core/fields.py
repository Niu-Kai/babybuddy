# -*- coding: utf-8 -*-
import datetime

from django import forms
from django.utils import timezone
from django.utils.translation import gettext as _


class NapStartMaxTimeField(forms.TimeField):
    def validate(self, value):
        from core.models import Sleep

        if value < Sleep.settings.nap_start_min:
            raise forms.ValidationError(
                _(
                    "Nap start max. value %(max)s must be greater than nap start min. value %(min)s."
                ),
                code="invalid_nap_start_max",
                params={"max": value, "min": Sleep.settings.nap_start_min},
            )


class NapStartMinTimeField(forms.TimeField):
    def validate(self, value):
        from core.models import Sleep

        if value > Sleep.settings.nap_start_max:
            raise forms.ValidationError(
                _(
                    "Nap start min. value %(min)s must be less than nap start max. value %(max)s."
                ),
                code="invalid_nap_start_min",
                params={"min": value, "max": Sleep.settings.nap_start_max},
            )


class DateTimeField(forms.DateTimeField):
    """
    Accepts local times that fall in a daylight saving transition instead of
    rejecting them (see babybuddy/babybuddy#174).

    A time in the repeated hour of a "fall back" transition is taken as its
    first occurrence; a time in the skipped hour of a "spring forward"
    transition is moved forward by the length of the gap, which is what most
    clocks and calendars do.
    """

    def to_python(self, value):
        try:
            return super().to_python(value)
        except forms.ValidationError as error:
            if error.code != "ambiguous_timezone":
                raise
        naive = self._parse_naive(value)
        current_timezone = timezone.get_current_timezone()
        aware = naive.replace(tzinfo=current_timezone, fold=0)
        # Round-tripping through UTC reveals a non-existent ("imaginary") time.
        if (
            aware.astimezone(datetime.timezone.utc)
            .astimezone(current_timezone)
            .replace(tzinfo=None)
            != naive
        ):
            gap = aware.replace(fold=1).utcoffset() - aware.utcoffset()
            aware = (naive + gap).replace(tzinfo=current_timezone)
        return aware

    def _parse_naive(self, value):
        if isinstance(value, datetime.datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)
        value = value.strip()
        try:
            return datetime.datetime.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            pass
        for input_format in self.input_formats:
            try:
                return datetime.datetime.strptime(value, input_format)
            except (ValueError, TypeError):
                continue
        raise forms.ValidationError(self.error_messages["invalid"], code="invalid")


class FloatField(forms.FloatField):
    """
    Accepts a comma as the decimal separator (e.g. "3,5"), which some mobile
    keyboards produce and the browser then submits verbatim
    (see babybuddy/babybuddy#1000).
    """

    def to_python(self, value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.count(",") == 1 and "." not in stripped:
                value = stripped.replace(",", ".")
        return super().to_python(value)
