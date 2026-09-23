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
    """Offset-aware input is exact; ambiguous naive input must be clarified."""


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
