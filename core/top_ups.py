"""A bottle supplement belongs to its nursing session, never a second feeding row."""

import datetime
import math
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone, formats
from django.utils.translation import gettext_lazy as _

TOP_UP_FIELDS = (
    "top_up_at",
    "top_up_type",
    "top_up_amount",
    "top_up_secondary_type",
    "top_up_secondary_amount",
)


def validate_top_up(entry):
    from core.feeding import BREAST_METHODS
    from core.models import validate_time

    if not entry.top_up_at:
        if any(getattr(entry, key) not in (None, "") for key in TOP_UP_FIELDS[1:]):
            raise ValidationError(
                {"top_up_at": _("Choose the top-up bottle date and time.")}
            )
        return
    errors = {}
    if entry.method not in BREAST_METHODS or entry.type != "breast milk":
        errors["method"] = _("A top-up bottle must be linked to a nursing session.")
    validate_time(entry.top_up_at, "top_up_at")
    if entry.end and entry.top_up_at.astimezone(
        datetime.timezone.utc
    ) < entry.end.astimezone(datetime.timezone.utc):
        errors["top_up_at"] = _("The top-up bottle cannot start before nursing ends.")
    milk_types = {"breast milk", "formula", "fortified breast milk"}
    if entry.top_up_type not in milk_types:
        errors["top_up_type"] = _("Choose the top-up milk type.")
    for field in ("top_up_amount", "top_up_secondary_amount"):
        value = getattr(entry, field)
        if value is not None and (not math.isfinite(value) or value <= 0):
            errors[field] = _("Enter an amount greater than zero.")
    if entry.top_up_amount is None:
        errors["top_up_amount"] = _("Enter the top-up bottle amount.")
    if entry.top_up_secondary_type or entry.top_up_secondary_amount is not None:
        if (
            entry.top_up_secondary_type not in milk_types
            or entry.top_up_secondary_type == entry.top_up_type
        ):
            errors["top_up_secondary_type"] = _("Choose a different second milk type.")
        if entry.top_up_secondary_amount is None:
            errors["top_up_secondary_amount"] = _("Enter the second milk amount.")
    if errors:
        raise ValidationError(errors)


def amount_parts(entry):
    """Time, milk type and canonical quantity; each quantity appears once."""
    for at, kind, amount in (
        (entry.start, entry.type, entry.amount),
        (entry.start, entry.secondary_type, entry.secondary_amount),
        (entry.top_up_at, entry.top_up_type, entry.top_up_amount),
        (entry.top_up_at, entry.top_up_secondary_type, entry.top_up_secondary_amount),
    ):
        if at and kind and kind != "solid food" and amount is not None:
            yield at, kind, amount


def top_up_summary(entry):
    from core.units import entry_value

    if not entry.top_up_at:
        return ""
    amounts = (
        entry.get_top_up_type_display() + ": " + entry_value(entry, "top_up_amount")
    )
    if entry.top_up_secondary_amount is not None:
        amounts += (
            " + "
            + entry.get_top_up_secondary_type_display()
            + ": "
            + entry_value(entry, "top_up_secondary_amount")
        )
    return (
        _("Top-up bottle")
        + " · "
        + formats.date_format(
            timezone.localtime(entry.top_up_at), "SHORT_DATETIME_FORMAT"
        )
        + " · "
        + amounts
    )


def setup_top_up_form(form):
    from core.entry_timing import time_widget, TIME_FORMATS, clock_format
    from babybuddy.widgets import DateInput
    from django.core import signing

    form.fields["top_up_enabled"] = forms.BooleanField(
        required=False, label=_("Add a top-up bottle")
    )
    form.fields["top_up_date"] = forms.DateField(
        required=False, label=_("Bottle date"), widget=DateInput()
    )
    form.fields["top_up_time"] = forms.TimeField(
        required=False,
        label=_("Bottle time"),
        widget=time_widget(form.user),
        input_formats=TIME_FORMATS,
    )
    form.fields["top_up_occurrence"] = forms.ChoiceField(
        required=False,
        choices=[("", ""), ("0", _("First occurrence")), ("1", _("Second occurrence"))],
        label=_("Which occurrence?"),
        widget=forms.HiddenInput(),
    )
    form.fields["top_up_reference"] = forms.CharField(
        required=False, widget=forms.HiddenInput()
    )
    form.fields["top_up_type"].label = _("Milk type")
    form.fields["top_up_amount"].label = _("Amount")
    form.fields["top_up_secondary_type"].label = _("Second type")
    form.fields["top_up_secondary_amount"].label = _("Second amount")
    form.fields["top_up_at"].widget = forms.HiddenInput()
    now = timezone.localtime(form.instance.top_up_at or timezone.now()).replace(
        second=0, microsecond=0
    )
    form.initial.update(
        top_up_enabled=bool(form.instance.top_up_at),
        top_up_date=now.date(),
        top_up_time=now.strftime(clock_format(form.user)),
        top_up_reference=signing.dumps(now.isoformat(), salt="entry-time"),
    )
    form.fieldsets = list(form.fieldsets)
    form.fieldsets.insert(
        -1,
        {
            "layout": "top_up",
            "fields": [
                "top_up_enabled",
                "top_up_date",
                "top_up_time",
                "top_up_occurrence",
                "top_up_type",
                "top_up_amount",
                "top_up_secondary_type",
                "top_up_secondary_amount",
                "top_up_at",
                "top_up_reference",
            ],
        },
    )


def clean_top_up_form(form, data):
    # Older clients omit the new controls; preserve saved supplements.
    if form.add_prefix("top_up_reference") not in form.data:
        for key in TOP_UP_FIELDS:
            data[key] = getattr(form.instance, key)
        return
    if not data.get("top_up_enabled"):
        for key in TOP_UP_FIELDS:
            data[key] = "" if key.endswith("type") else None
        return
    for field in ("top_up_date", "top_up_time"):
        if field in form.errors:
            return
        if not data.get(field):
            form.add_error(field, _("This field is required."))
            return
    from core.local_times import configure, resolve

    clock = forms.Form()
    configure(clock)
    clock.fields["start_time"] = forms.TimeField(required=False)
    clock.cleaned_data = {}
    clock._errors = forms.utils.ErrorDict()
    at = resolve(
        clock,
        {
            "appointment_date": data["top_up_date"],
            "start_time": data["top_up_time"],
            "time_occurrence": data.get("top_up_occurrence"),
            "entry_reference": data.get("top_up_reference"),
        },
    )
    form.fields["top_up_occurrence"].widget = clock.fields["time_occurrence"].widget
    form.fields["top_up_occurrence"].choices = clock.fields["time_occurrence"].choices
    for field, errors in clock.errors.items():
        form.add_error(
            "top_up_occurrence" if field == "time_occurrence" else "top_up_time", errors
        )
    data["top_up_at"] = at
