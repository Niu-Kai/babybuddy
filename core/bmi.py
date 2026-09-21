"""BMI history derived from known-unit weight and height measurements."""

import math
from collections import defaultdict

from django.db import transaction
from django.db.models import F, Subquery


def rebuild_bmi(child_id, *, using="default", apps=None):
    if apps is None:
        from django.apps import apps
    Child = apps.get_model("core", "Child")
    Weight = apps.get_model("core", "Weight")
    Height = apps.get_model("core", "Height")
    BMI = apps.get_model("core", "BMI")
    with transaction.atomic(using=using):
        if (
            not Child.objects.using(using)
            .select_for_update()
            .filter(pk=child_id)
            .exists()
        ):
            return
        changes = defaultdict(dict)
        for weight in (
            Weight.objects.using(using)
            .filter(child_id=child_id)
            .only("pk", "date", "time", "weight", "entry_unit")
            .order_by("date", F("time").asc(nulls_first=True), "pk")
        ):
            changes[weight.date]["weight"] = weight
        for height in (
            Height.objects.using(using)
            .filter(child_id=child_id)
            .only("pk", "date", "height", "entry_unit")
            .order_by("date", "pk")
        ):
            changes[height.date]["height"] = height
        desired = {}
        weight = height = None
        for date, values in sorted(changes.items()):
            weight = values.get("weight", weight)
            height = values.get("height", height)
            if not weight or not height:
                continue
            if weight.entry_unit not in {"kg", "lb", "oz"} or height.entry_unit not in {
                "cm",
                "in",
            }:
                continue
            if not (
                math.isfinite(weight.weight)
                and math.isfinite(height.height)
                and weight.weight > 0
                and height.height > 0
            ):
                continue
            # Values with explicit entry units are already stored in kg and cm.
            try:
                value = weight.weight / (height.height / 100) ** 2
            except (ZeroDivisionError, OverflowError):
                continue
            if math.isfinite(value):
                desired[date] = (value, weight.pk, height.pk)
        existing = BMI.objects.using(using).filter(
            child_id=child_id, is_calculated=True
        )
        by_date = {entry.date: entry for entry in existing}
        remove = [entry.pk for date, entry in by_date.items() if date not in desired]
        if remove:
            BMI.objects.using(using).filter(pk__in=remove).delete()
        create, update = [], []
        for date, (value, weight_id, height_id) in desired.items():
            entry = by_date.get(date)
            if entry is None:
                create.append(
                    BMI(
                        child_id=child_id,
                        date=date,
                        bmi=value,
                        is_calculated=True,
                        source_weight_id=weight_id,
                        source_height_id=height_id,
                    )
                )
            elif (entry.bmi, entry.source_weight_id, entry.source_height_id) != (
                value,
                weight_id,
                height_id,
            ):
                entry.bmi, entry.source_weight_id, entry.source_height_id = (
                    value,
                    weight_id,
                    height_id,
                )
                update.append(entry)
        BMI.objects.using(using).bulk_create(create)
        if update:
            BMI.objects.using(using).bulk_update(
                update, ["bmi", "source_weight", "source_height"]
            )


def current_bmi(child):
    from core.models import BMI, Weight, Height

    weight = Weight.objects.filter(child=child).values("pk")[:1]
    height = Height.objects.filter(child=child).values("pk")[:1]
    return (
        BMI.objects.filter(
            child=child,
            source_weight_id=Subquery(weight),
            source_height_id=Subquery(height),
        )
        .select_related("source_weight", "source_height")
        .first()
    )


def connect():
    from core.models import Weight, Height, Child
    from django.db.models.signals import pre_save, post_save, post_delete

    def before_save(sender, instance, raw=False, using="default", **kwargs):
        if not raw and instance.pk:
            instance._bmi_previous_child = (
                sender.objects.using(using)
                .filter(pk=instance.pk)
                .values_list("child_id", flat=True)
                .first()
            )

    def changed(sender, instance, raw=False, using="default", origin=None, **kwargs):
        if raw or isinstance(origin, Child) or getattr(origin, "model", None) is Child:
            return
        for child_id in {
            instance.child_id,
            getattr(instance, "_bmi_previous_child", None),
        } - {None}:
            rebuild_bmi(child_id, using=using)

    for model in (Weight, Height):
        pre_save.connect(
            before_save,
            sender=model,
            weak=False,
            dispatch_uid="bmi-before-" + model.__name__,
        )
        post_save.connect(
            changed, sender=model, weak=False, dispatch_uid="bmi-save-" + model.__name__
        )
        post_delete.connect(
            changed,
            sender=model,
            weak=False,
            dispatch_uid="bmi-delete-" + model.__name__,
        )
