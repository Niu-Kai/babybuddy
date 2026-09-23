"""Optional side quantities retain the existing amount as the session total."""

import math
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def set_pumping_total(entry):
    for field in ("amount", "left_amount", "right_amount"):
        value = getattr(entry, field)
        if value is None:
            continue
        try:
            value = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValidationError({field: _("Enter a nonnegative amount.")})
        if not math.isfinite(value) or value < 0:
            raise ValidationError({field: _("Enter a nonnegative amount.")})
        setattr(entry, field, value)
    left, right = entry.left_amount, entry.right_amount
    if left is not None or right is not None:
        entry.amount = (left or 0) + (right or 0)
        entry.side = (
            "both"
            if left is not None and right is not None
            else "left" if left is not None else "right"
        )
    elif entry.amount is None:
        raise ValidationError(
            {"amount": _("Enter a total or an amount for each measured side.")}
        )
