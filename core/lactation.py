"""Household milk-expression history. Never infer nursing from bottle feeds."""

from datetime import timedelta
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from core.models import Feeding, Pumping
from core.units import convert, preferred_unit

NURSING_METHODS = ("left breast", "right breast", "both breasts")


def sessions(user):
    now = timezone.now()
    pumps = Pumping.objects.filter(start__lte=now, end__lte=now)
    nursing = Feeding.objects.filter(
        method__in=NURSING_METHODS, start__lte=now, end__lte=now
    )
    if not user.has_perm("core.view_pumping"):
        pumps = pumps.none()
    if not user.has_perm("core.view_feeding"):
        nursing = nursing.none()
    return pumps, nursing


def overview(user):
    pumps, nursing = sessions(user)
    last_pump = pumps.order_by("-end", "-pk").first()
    last_nursing = nursing.order_by("-end", "-pk").first()
    latest = max(
        (e for e in (last_pump, last_nursing) if e), key=lambda e: e.end, default=None
    )
    today = pumps.filter(start__date=timezone.localdate())
    totals = today.aggregate(count=Count("pk"))
    known = today.filter(entry_unit__in=("mL", "fl oz"))
    amount = known.aggregate(amount=Sum("amount"))["amount"] or 0
    unit = preferred_unit(user.settings, "pumping")
    sides = []
    for side in ("left", "right"):
        pump = pumps.filter(side__in=(side, "both")).order_by("-end").first()
        nurse = (
            nursing.filter(method__in=(side + " breast", "both breasts"))
            .order_by("-end")
            .first()
        )
        recent = max((e for e in (pump, nurse) if e), key=lambda e: e.end, default=None)
        sides.append(
            {"label": _("Left") if side == "left" else _("Right"), "last": recent}
        )
    minutes = user.settings.pumping_reminder_minutes
    basis = user.settings.pumping_reminder_basis
    reference = last_pump if basis == "pumping" else latest
    due = reference.end + timedelta(minutes=minutes) if reference and minutes else None
    return {
        "last_pump": last_pump,
        "last_nursing": last_nursing,
        "latest_session": latest,
        "latest_kind": (
            _("Pumping") if latest and isinstance(latest, Pumping) else _("Nursing")
        ),
        "pumping_count": totals["count"],
        "nursing_count": nursing.filter(start__date=timezone.localdate()).count(),
        "pumped_amount": convert(amount, "mL", unit),
        "pumped_unit": unit,
        "unknown_amount_count": today.exclude(entry_unit__in=("mL", "fl oz")).count(),
        "sides": sides,
        "reminder_enabled": bool(minutes),
        "reminder_due": due,
        "reminder_ready": bool(due and due <= timezone.now()),
        "reminder_basis": (
            _("Pumping only") if basis == "pumping" else _("Pumping or nursing")
        ),
    }
