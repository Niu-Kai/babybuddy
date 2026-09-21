"""Shared, minute-precision care-entry controls; stored timestamps stay intact."""

import datetime

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from babybuddy.widgets import DateInput
from core import fields
from core.widgets import AppointmentTimeInput, AppointmentDurationInput

TIME_FORMATS = ["%H:%M", "%I:%M %p"]


def clock_format(user):
    return "%H:%M" if user and user.settings.use_24_hour_time else "%I:%M %p"


def time_widget(user):
    fmt = clock_format(user)
    values = [
        datetime.time(hour, minute).strftime(fmt)
        for hour in range(24)
        for minute in (0, 15, 30, 45)
    ]
    return AppointmentTimeInput(
        format=fmt,
        attrs={
            "placeholder": "13:30" if fmt == "%H:%M" else "1:30 PM",
            "autocomplete": "off",
        },
        choices=[(value, value) for value in values],
        choice_label=_("Choose a time"),
        choice_kind="time",
    )


def duration_widget(optional=True):
    choices = [
        ("5", _("5 minutes")),
        ("10", _("10 minutes")),
        ("15", _("15 minutes")),
        ("30", _("30 minutes")),
        ("45", _("45 minutes")),
        ("60", _("1 hour (60 minutes)")),
        ("90", _("1.5 hours (90 minutes)")),
        ("120", _("2 hours (120 minutes)")),
    ]
    if optional:
        choices.append(("", _("Without a duration")))
    return AppointmentDurationInput(
        attrs={"inputmode": "decimal", "autocomplete": "off", "placeholder": "30"},
        choices=choices,
        choice_label=_("Choose a duration"),
        choice_kind="duration",
    )


def setup_entry_timing(form):
    if form._meta.model._meta.model_name == "appointment":
        return
    now = timezone.localtime().replace(second=0, microsecond=0)
    # Date-only measurements and optional standalone times use the same defaults.
    for name, field in form.fields.items():
        if isinstance(field, forms.DateField) and not isinstance(
            field, forms.DateTimeField
        ):
            if not form.instance.pk:
                form.initial.setdefault(name, now.date())
        elif isinstance(field, forms.TimeField):
            field.widget = time_widget(form.user)
            field.input_formats = TIME_FORMATS
            if not form.instance.pk:
                form.initial.setdefault(name, now.time())
    timestamp = next(
        (
            name
            for name in ("start", "time")
            if isinstance(form.fields.get(name), forms.DateTimeField)
        ),
        None,
    )
    if timestamp is None:
        return
    # Accept older clients and bookmarked forms without changing their contract.
    if form.is_bound and not any(
        form.add_prefix(name) in form.data
        for name in ("appointment_date", "start_time", "duration_minutes")
    ):
        return
    paired = "end" in form.fields
    original = form.initial.get(timestamp) or (
        getattr(form.instance, timestamp) if form.instance.pk else now
    )
    original = timezone.localtime(original)
    form.entry_original_start = original
    form._entry_timestamp = timestamp
    form.entry_timing = True
    form.entry_has_duration = paired
    form.entry_model = form._meta.model._meta.model_name
    form.fields[timestamp].required = False
    form.fields[timestamp].widget = forms.HiddenInput()
    form.fields["appointment_date"] = forms.DateField(
        label=_("Date"), widget=DateInput()
    )
    form.fields["start_time"] = forms.TimeField(
        label=_("Start time") if paired else _("Time"),
        input_formats=TIME_FORMATS,
        widget=time_widget(form.user),
    )
    form.initial["appointment_date"] = original.date().isoformat()
    form.initial["start_time"] = original.strftime(clock_format(form.user))
    timing_names = ["appointment_date", "start_time"]
    if paired:
        optional = form.entry_model == "feeding"
        form.fields["end"].required = False
        form.fields["end"].widget = forms.HiddenInput()
        form.fields["duration_minutes"] = fields.FloatField(
            label=_("Duration (minutes)"),
            required=not optional,
            min_value=0,
            widget=duration_widget(optional),
            help_text=(
                _(
                    "Choose a duration or type the number of minutes. Leave blank if unknown."
                )
                if optional
                else _("Choose a duration or type the number of minutes.")
            ),
        )
        end = form.initial.get("end")
        form.initial["duration_minutes"] = (
            (
                end.astimezone(datetime.timezone.utc)
                - original.astimezone(datetime.timezone.utc)
            ).total_seconds()
            / 60
            if end
            else None
        )
        timing_names.append("duration_minutes")
    old_sets = getattr(
        form,
        "fieldsets",
        [{"fields": [name for name in form.fields if name not in timing_names]}],
    )
    new_sets = []
    for fieldset in old_sets:
        pending = []
        for name in fieldset["fields"]:
            if name == timestamp:
                if pending:
                    new_sets.append({**fieldset, "fields": pending})
                    pending = []
                new_sets.append({"fields": timing_names, "layout": "entry_time"})
            elif not (paired and name == "end"):
                pending.append(name)
        if pending:
            new_sets.append({**fieldset, "fields": pending})
    form.fieldsets = new_sets


def clean_entry_timing(form, data):
    if form.instance.pk:
        for name, field in form.fields.items():
            if isinstance(field, forms.TimeField) and hasattr(form.instance, name):
                original = getattr(form.instance, name)
                if original and data.get(name) == original.replace(
                    second=0, microsecond=0
                ):
                    data[name] = original
    if not getattr(form, "entry_timing", False):
        return
    names = ["appointment_date", "start_time"]
    if form.entry_has_duration:
        names.append("duration_minutes")
    if any(name in form.errors for name in names):
        return
    try:
        start = fields.DateTimeField().clean(
            datetime.datetime.combine(data["appointment_date"], data["start_time"])
        )
        original = form.entry_original_start
        # Preserve precise old/timer timestamps when their visible date/time is unchanged.
        if (
            original.date() == data["appointment_date"]
            and original.time().replace(second=0, microsecond=0) == data["start_time"]
        ):
            start = original
        data[form._entry_timestamp] = start
        if form.entry_has_duration:
            minutes = data.get("duration_minutes")
            data["end"] = timezone.localtime(
                start.astimezone(datetime.timezone.utc)
                + datetime.timedelta(minutes=minutes or 0)
            )
    except (OverflowError, ValueError, forms.ValidationError):
        form.add_error(
            "duration_minutes" if form.entry_has_duration else "start_time",
            _("Choose a valid date, time, and duration."),
        )
