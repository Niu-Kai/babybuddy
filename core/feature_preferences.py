"""Presentation preferences do not grant or revoke permissions."""

from django import forms
from django.utils.translation import gettext_lazy as _
from core.presentation import ACTIVITIES, MEASUREMENTS


def activity_choices():
    return [
        (key.replace("-", ""), _(label))
        for _group, entries in ACTIVITIES + MEASUREMENTS
        for key, label in entries
    ]


OPTIONAL_FIELDS = {
    "notes": (_("Notes"), ("notes",)),
    "tags": (_("Tags"), ("tags",)),
    "feeding_amounts": (
        _("Feeding amounts and mixed bottle fields"),
        (
            "amount",
            "secondary_type",
            "secondary_amount",
            "entry_unit",
            "top_up_enabled",
            "top_up_date",
            "top_up_time",
            "top_up_occurrence",
            "top_up_at",
            "top_up_type",
            "top_up_amount",
            "top_up_secondary_type",
            "top_up_secondary_amount",
            "top_up_reference",
        ),
    ),
    "diaper_details": (_("Diaper color and amount"), ("color", "amount")),
}


def apply_fields(form):
    prefs = getattr(getattr(form, "user", None), "settings", None)
    hidden = getattr(prefs, "hidden_entry_fields", []) or []
    model = form._meta.model._meta.model_name
    for key in hidden:
        if (
            key not in OPTIONAL_FIELDS
            or (key == "feeding_amounts" and model != "feeding")
            or (key == "diaper_details" and model != "diaperchange")
        ):
            continue
        for name in OPTIONAL_FIELDS[key][1]:
            field = form.fields.get(name)
            if field is not None and not field.required:
                field.widget = forms.HiddenInput()
                field.disabled = True
    form.field_preferences_applied = True
