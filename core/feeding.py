"""Feeding validation shared by browser forms and API clients."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

BREAST_METHODS = {"left breast", "right breast", "both breasts"}


def validate_feeding_method(entry):
    types = {entry.type, entry.secondary_type} - {None, ""}
    if entry.method in BREAST_METHODS and types != {"breast milk"}:
        raise ValidationError(
            {
                "method": _(
                    "Breastfeeding requires breast milk. Use the top-up bottle fields for a bottle supplement."
                )
            }
        )
    if entry.method == "bottle" and "solid food" in types:
        raise ValidationError(
            {"method": _("Choose caregiver fed or self fed for solid food.")}
        )


def validate_timer_context(value):
    """Only documented defaults, never arbitrary model attributes."""
    from core.models import Feeding

    if not isinstance(value, dict) or set(value) - {"activity", "type", "method"}:
        raise ValidationError(_("Use an object with activity, type, and method only."))
    activity = value.get("activity")
    if value and activity not in {
        "feeding",
        "sleep",
        "pumping",
        "tummytime",
        "bathtime",
    }:
        raise ValidationError(_("Choose a supported timer activity."))
    for name in ("type", "method"):
        if name in value:
            if activity != "feeding" or value[name] not in dict(
                Feeding._meta.get_field(name).choices
            ):
                raise ValidationError(_("Choose valid feeding defaults."))
    if value.get("type") and value.get("method"):
        validate_feeding_method(Feeding(type=value["type"], method=value["method"]))
