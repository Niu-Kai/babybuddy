"""Resolve wall-clock input without silently shifting it across DST changes."""

import datetime
from django import forms
from django.core import signing
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def candidates(naive):
    zone = timezone.get_current_timezone()
    result = []
    for fold in (0, 1):
        instant = naive.replace(tzinfo=zone, fold=fold)
        if (
            instant.astimezone(datetime.timezone.utc)
            .astimezone(zone)
            .replace(tzinfo=None)
            == naive
        ):
            if not result or instant.utcoffset() != result[0].utcoffset():
                result.append(instant)
    return result


def configure(form, reference=None):
    form.fields["time_occurrence"] = forms.ChoiceField(
        label=_("Which occurrence?"),
        required=False,
        choices=[
            ("", _("Choose an occurrence")),
            ("0", _("First occurrence")),
            ("1", _("Second occurrence")),
        ],
        widget=forms.HiddenInput(),
    )
    form.fields["entry_reference"] = forms.CharField(
        required=False, widget=forms.HiddenInput()
    )
    if reference:
        form.initial["entry_reference"] = signing.dumps(
            reference.isoformat(), salt="entry-time"
        )


def resolve(form, data, reference=None):
    naive = datetime.datetime.combine(data["appointment_date"], data["start_time"])
    if reference is None and data.get("entry_reference"):
        try:
            reference = datetime.datetime.fromisoformat(
                signing.loads(
                    data["entry_reference"], salt="entry-time", max_age=7 * 86400
                )
            )
        except (signing.BadSignature, ValueError, TypeError):
            pass
    if (
        reference is not None
        and timezone.is_aware(reference)
        and not data.get("time_occurrence")
    ):
        local = timezone.localtime(reference)
        if local.replace(second=0, microsecond=0, tzinfo=None) == naive:
            return local
    options = candidates(naive)
    if not options:
        form.add_error(
            "start_time",
            _(
                "This time was skipped when the clocks moved forward. Choose a valid time."
            ),
        )
        return None
    if len(options) == 1:
        return options[0]
    field = form.fields["time_occurrence"]
    field.widget = forms.Select()
    field.choices = [("", _("Choose an occurrence"))] + [
        (
            str(index),
            _("%(occurrence)s %(time)s (%(zone)s, UTC%(offset)s)")
            % {
                "occurrence": _("First") if index == 0 else _("Second"),
                "time": option.strftime("%H:%M"),
                "zone": option.tzname(),
                "offset": option.strftime("%z"),
            },
        )
        for index, option in enumerate(options)
    ]
    choice = data.get("time_occurrence")
    if choice not in {"0", "1"}:
        form.add_error(
            "time_occurrence",
            _(
                "This time occurs twice when clocks move back. Choose the first or second occurrence."
            ),
        )
        return None
    return options[int(choice)]
