"""Explicit units for measurements; legacy records are never silently relabeled."""

from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _

SPECS = {
    "height": (("height",), "cm", "in", (("cm", "cm"), ("in", "in"))),
    "headcircumference": (
        ("head_circumference",),
        "cm",
        "in",
        (("cm", "cm"), ("in", "in")),
    ),
    "weight": (("weight",), "kg", "lb", (("kg", "kg"), ("lb", "lbs"), ("oz", "oz"))),
    "temperature": (("temperature",), "C", "F", (("C", "°C"), ("F", "°F"))),
    "feeding": (
        ("amount", "secondary_amount"),
        "mL",
        "fl oz",
        (("mL", "mL"), ("fl oz", "fl oz (US)")),
    ),
    "pumping": (("amount",), "mL", "fl oz", (("mL", "mL"), ("fl oz", "fl oz (US)"))),
}
UNIT_PREFERENCE_FIELDS = {
    "height": "length_unit",
    "headcircumference": "length_unit",
    "weight": "weight_unit",
    "temperature": "temperature_unit",
    "feeding": "liquid_unit",
    "pumping": "liquid_unit",
}


def preferred_unit(settings, model):
    spec = SPECS[model]
    unit = getattr(settings, UNIT_PREFERENCE_FIELDS[model], spec[1])
    return unit if unit in dict(spec[3]) else spec[1]


FACTORS = {
    "cm": Decimal(1),
    "in": Decimal("2.54"),
    "kg": Decimal(1),
    "lb": Decimal("0.45359237"),
    "oz": Decimal("0.028349523125"),
    "mL": Decimal(1),
    "fl oz": Decimal("29.5735295625"),
}


def convert(value, source, target):
    if value is None or source == target:
        return value
    number = Decimal(str(value))
    if source in ("C", "F") and target in ("C", "F"):
        return float((number - 32) * 5 / 9 if source == "F" else number * 9 / 5 + 32)
    return float(number * FACTORS[source] / FACTORS[target])


def setup_unit_field(form):
    model = form._meta.model._meta.model_name
    spec = SPECS.get(model)
    if not spec:
        return
    fields, canonical, customary, choices = spec
    unit = (
        form.instance.entry_unit
        if form.instance.pk
        else preferred_unit(getattr(form.user, "settings", None), model)
    )
    form.fields["entry_unit"] = forms.ChoiceField(
        label=_("Entry unit"),
        choices=[("", _("Unit not recorded — choose to confirm"))] + list(choices),
        required=False,
    )
    form.initial["entry_unit"] = unit
    if form.instance.pk and form.instance.entry_unit:
        for field in fields:
            value = form.initial.get(field)
            if value is not None:
                form.initial[field] = convert(value, canonical, unit)
    form.fields["entry_unit"].widget.attrs["data-unit-fields"] = ",".join(fields)
    if form.instance.pk and not form.instance.entry_unit:
        form.fields["entry_unit"].help_text = _(
            "This older entry has no recorded unit. Choose the unit originally used before converting it."
        )
    else:
        form.fields["entry_unit"].help_text = _(
            "Choose the unit you are entering. Other caregivers can view the same measurement in their preferred units."
        )
    for field in fields:
        form.fields[field].help_text = _("Use the selected entry unit.")
    if hasattr(form, "fieldsets"):
        form.fieldsets = [
            {**fieldset, "fields": list(fieldset["fields"])}
            for fieldset in form.fieldsets
        ]
        for fieldset in form.fieldsets:
            if fields[0] in fieldset["fields"]:
                fieldset["fields"].insert(
                    fieldset["fields"].index(fields[0]) + 1, "entry_unit"
                )
                break


def clean_unit_fields(form, data):
    spec = SPECS.get(form._meta.model._meta.model_name)
    if not spec or "entry_unit" in form.errors:
        return
    fields, canonical, _, _ = spec
    unit = data.get("entry_unit")
    if not unit:
        # Older integrations and tests can still submit their original raw
        # values; editing an explicit-unit entry may never erase its meaning.
        unit = form.instance.entry_unit if form.instance.pk else ""
    if form._meta.model._meta.model_name == "feeding" and (
        data.get("type") == "solid food" or data.get("secondary_type") == "solid food"
    ):
        if unit:
            form.add_error(
                "entry_unit",
                _(
                    "Liquid units do not apply to solid food. Choose 'Unit not recorded' or use Foods to describe a serving."
                ),
            )
        return
    if unit:
        for field in fields:
            if data.get(field) is not None:
                data[field] = convert(data[field], unit, canonical)
        form.instance.entry_unit = unit


def entry_value(entry, field):
    """Plain-text quantity in its originally entered unit for activity summaries."""
    value = getattr(entry, field, None)
    if value is None:
        return ""
    spec = SPECS.get(entry._meta.model_name)
    unit = getattr(entry, "entry_unit", "")
    if not spec or not unit:
        return f"{value:g}"
    converted = convert(value, spec[1], unit)
    label = dict(spec[3])[unit]
    return f"{converted:.2f}".rstrip("0").rstrip(".") + " " + label
