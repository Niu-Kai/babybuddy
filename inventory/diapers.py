"""Transactional, entry-linked diaper consumption. Shared stock, matched per child."""

from .sizing import same_diaper_size
from django.db.models import F
from django.utils import timezone
from .models import ChildSupplyProfile, StockItem, StockMovement, DiaperStockUsage

MESSAGES = {
    "missing": "No diaper supply matches this child's selected size or age range.",
    "ambiguous": "More than one diaper supply matches. Choose a diaper supply under Manage children.",
    "invalid": "The selected diaper supply is unavailable. Choose another under Manage children.",
    "empty": "The child's diaper supply is out of stock. Review the inventory count.",
}


def supply_available(item):
    return (
        item.category == "diapers"
        and item.unit in {"diapers", "items"}
        and not item.archived
        and item.stage == "current"
        and not item.expired
    )


def supply_matches(item, child, profile=None):
    if not supply_available(item):
        return False
    # An explicit supply is a caregiver's fit override, including larger diapers.
    if profile and profile.diaper_stock_id == item.pk:
        return True
    size = profile.diaper_size if profile else ""
    if size:
        return bool(item.size and same_diaper_size(item.size, size))
    # Age matching is only based on ranges entered by the household, never
    # inferred from a manufacturer's weight-based diaper size.
    if item.min_age_months is None and item.max_age_months is None:
        return False
    today, birth = timezone.localdate(), child.birth_date
    if birth > today:
        return False
    age = (
        (today.year - birth.year) * 12
        + today.month
        - birth.month
        - (today.day < birth.day)
    )
    return not (
        (item.min_age_months is not None and age < item.min_age_months)
        or (item.max_age_months is not None and age > item.max_age_months)
    )


def select_supply(child, profile, items):
    """Use the same assignment rules for consumption and restock forecasts."""
    if profile and not profile.auto_deduct_diapers:
        return None, "off"
    if profile and profile.diaper_stock_id:
        item = next(
            (item for item in items if item.pk == profile.diaper_stock_id), None
        )
        if item and supply_matches(item, child, profile):
            return item.pk, ""
        return None, "invalid"
    candidates = [item for item in items if supply_matches(item, child, profile)]
    if len(candidates) == 1:
        return candidates[0].pk, ""
    return None, "ambiguous" if candidates else "missing"


def supply_for(child, using):
    profile = ChildSupplyProfile.objects.using(using).filter(child=child).first()
    items = StockItem.objects.using(using).filter(category="diapers")
    target, status = select_supply(child, profile, items)
    return target, status, profile


def movement(item, change, entry, note, using):
    StockItem.objects.using(using).filter(pk=item.pk).update(
        quantity=F("quantity") + change, updated_at=timezone.now(), snoozed_until=None
    )
    item.refresh_from_db(using=using, fields=["quantity"])
    StockMovement.objects.using(using).create(
        item=item,
        action="use" if change < 0 else "add",
        change=change,
        balance=item.quantity,
        user_id=getattr(entry, "_inventory_actor_id", entry.created_by_id),
        note=f"Diaper entry #{entry.pk}: {note}"[:160],
    )


def saved(sender, instance, created, raw=False, using="default", **kwargs):
    if raw or getattr(instance, "_historical_import", False):
        return
    usage = (
        DiaperStockUsage.objects.using(using)
        .select_for_update()
        .filter(entry_id=instance.pk)
        .first()
    )
    # Pre-feature entries and fixture/import rows have no linked usage. Editing
    # them must not silently charge today's inventory for historical care.
    if not usage and not created:
        return
    from core.models import Child

    child_id = (
        sender.objects.using(using)
        .values_list("child_id", flat=True)
        .get(pk=instance.pk)
    )
    if usage and usage.child_id_at_save == child_id:
        instance._inventory_status = usage.status
        return
    child = Child.objects.using(using).get(pk=child_id)
    target, status, profile = supply_for(child, using)
    old_item_id = usage.item_id if usage and usage.deducted else None
    # Lock both supplies in deterministic order when transferring a child's entry.
    ids = sorted({pk for pk in (old_item_id, target) if pk})
    items = {
        item.pk: item
        for item in StockItem.objects.using(using)
        .select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
    }
    if old_item_id in items:
        movement(items[old_item_id], 1, instance, "returned after child changed", using)
    item = items.get(target)
    deducted = False
    if item:
        if not supply_matches(item, child, profile):
            status = "invalid"
        elif (
            StockItem.objects.using(using)
            .filter(pk=item.pk, quantity__gte=1)
            .update(
                quantity=F("quantity") - 1,
                updated_at=timezone.now(),
                snoozed_until=None,
            )
        ):
            item.refresh_from_db(using=using, fields=["quantity"])
            StockMovement.objects.using(using).create(
                item=item,
                action="use",
                change=-1,
                balance=item.quantity,
                user_id=getattr(
                    instance, "_inventory_actor_id", instance.created_by_id
                ),
                note=f"Diaper entry #{instance.pk}: {child}"[:160],
            )
            deducted, status = True, "deducted"
        else:
            status = "empty"
    elif not status:
        status = "invalid"
    DiaperStockUsage.objects.using(using).update_or_create(
        entry_id=instance.pk,
        defaults=dict(
            child_id_at_save=child_id,
            item_id=item.pk if item else None,
            deducted=deducted,
            status=status,
        ),
    )
    instance._inventory_status = status


def deleting(sender, instance, using="default", origin=None, **kwargs):
    from core.models import Child

    # Deleting a child's entire history must not replenish already-used supplies.
    if isinstance(origin, Child) or getattr(origin, "model", None) is Child:
        return
    usage = (
        DiaperStockUsage.objects.using(using)
        .select_for_update()
        .filter(entry_id=instance.pk, deducted=True)
        .first()
    )
    if usage and usage.item_id:
        item = (
            StockItem.objects.using(using)
            .select_for_update()
            .filter(pk=usage.item_id)
            .first()
        )
        if item:
            movement(item, 1, instance, "returned after entry deleted", using)
        usage.deducted = False
        usage.save(using=using, update_fields=["deducted"])


def notify(request, entry):
    from django.contrib import messages

    status = getattr(entry, "_inventory_status", "")
    if status in MESSAGES:
        messages.warning(
            request, "Entry saved; diaper stock was not deducted. " + MESSAGES[status]
        )


def connect():
    from django.db.models.signals import post_save, pre_delete
    from core.models import DiaperChange

    post_save.connect(saved, sender=DiaperChange, dispatch_uid="inventory.diaper_saved")
    pre_delete.connect(
        deleting, sender=DiaperChange, dispatch_uid="inventory.diaper_deleted"
    )
