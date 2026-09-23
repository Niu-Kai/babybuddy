"""Read-only usage forecasts. Counts change only through recorded usage."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Min, Sum
from django.utils import timezone

NOTICE_DAYS = 14
RESTOCK_DAYS = 30
HISTORY_DAYS = 14


from core.access import unscoped


@unscoped()
def daily_rates(items):
    from core.models import Child, DiaperChange
    from .diapers import select_supply
    from .models import StockMovement

    items = list(items)
    rates = {item.pk: None for item in items}
    active = [item for item in items if not item.archived and item.stage == "current"]
    if not active:
        return rates
    today = timezone.localdate()
    start = timezone.make_aware(
        datetime.combine(today - timedelta(days=HISTORY_DAYS), time.min)
    )
    end = timezone.make_aware(datetime.combine(today, time.min))

    def per_day(row, count):
        # Exclude today's partial day, but include zero-use days after logging began.
        days = (today - timezone.localtime(row["first"]).date()).days
        return Decimal(count) / days

    diapers = [
        item
        for item in active
        if item.category == "diapers" and item.unit in {"diapers", "items"}
    ]
    if diapers:
        groups = {}
        for child in Child.objects.select_related("supply_profile"):
            profile = getattr(child, "supply_profile", None)
            target, _ = select_supply(child, profile, diapers)
            if target:
                groups.setdefault(target, []).append(child.pk)
        child_ids = [pk for group in groups.values() for pk in group]
        history = {
            row["child_id"]: row
            for row in DiaperChange.objects.filter(
                child_id__in=child_ids, time__gte=start, time__lt=end
            )
            .order_by()
            .values("child_id")
            .annotate(count=Count("pk"), first=Min("time"))
        }
        for target, children in groups.items():
            # Do not understate shared use when one child's recent logs are missing.
            if all(pk in history for pk in children):
                rates[target] = sum(
                    (per_day(history[pk], history[pk]["count"]) for pk in children),
                    Decimal(0),
                )

    # Other supplies use explicit Use stock records, never restocks/count corrections.
    other_ids = [item.pk for item in active if item.category != "diapers"]
    for row in (
        StockMovement.objects.filter(
            item_id__in=other_ids,
            action="use",
            change__lt=0,
            created_at__gte=start,
            created_at__lt=end,
        )
        .order_by()
        .values("item_id")
        .annotate(used=Sum("change"), first=Min("created_at"))
    ):
        rates[row["item_id"]] = per_day(row, -row["used"])
    return rates


def forecast_items(request):
    """Share one forecast snapshot across cards, shopping list, and navigation."""
    from .models import StockItem

    if not hasattr(request, "_inventory_forecast_items"):
        items = list(StockItem.objects.filter(archived=False).defer("notes"))
        rates = daily_rates(items)
        for item in items:
            item._daily_use_rate = rates[item.pk]
        request._inventory_forecast_items = items
    return request._inventory_forecast_items
