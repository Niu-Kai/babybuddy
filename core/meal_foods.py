from django.utils.translation import gettext_lazy as _

"""A feeding and its linked food exposures are saved in one transaction."""

import json
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from core.access import scoped
from core.models import Food


class MealFoodsWidget(forms.Widget):
    template_name = "core/widgets/meal_foods.html"

    def value_from_datadict(self, data, files, name):
        # Stable IDs preserve each exposure when a meal is edited.
        def values(key):
            if hasattr(data, "getlist"):
                return data.getlist(key)
            value = data.get(key, [])
            return value if isinstance(value, list) else [value]

        names = values(name + "_name")
        ids = values(name + "_id")
        reactions = values(name + "_reaction")
        return [
            {
                "id": ids[i] if i < len(ids) else "",
                "name": value,
                "reaction": reactions[i] if i < len(reactions) else "",
            }
            for i, value in enumerate(names)
        ]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                value = []
        context["rows"] = value or [{"name": "", "reaction": ""}]
        context["reactions"] = Food._meta.get_field("reaction").choices
        context["suggestions"] = getattr(self, "suggestions", [])
        return context


def normalize_foods(value):
    if not isinstance(value, list) or len(value) > 20:
        raise ValidationError(_("Add up to 20 foods per meal."))
    cleaned, seen = [], set()
    choices = dict(Food._meta.get_field("reaction").choices)
    for row in value:
        if not isinstance(row, dict) or set(row) - {"id", "name", "reaction"}:
            raise ValidationError(_("Each food needs a name and optional reaction."))
        name, reaction = row.get("name", ""), row.get("reaction") or ""
        if not isinstance(name, str) or not isinstance(reaction, str):
            raise ValidationError(_("Enter a food name and a valid reaction."))
        name = name.strip()
        if not name:
            if row.get("id") or reaction:
                raise ValidationError(_("Enter a name or remove the food row."))
            continue
        if len(name) > 255 or name.casefold() in seen:
            raise ValidationError(
                _("Use distinct food names, up to 255 characters each.")
            )
        if reaction and reaction not in choices:
            raise ValidationError(_("Choose a valid food reaction."))
        seen.add(name.casefold())
        pk = row.get("id")
        if pk not in (None, ""):
            try:
                pk = int(pk)
            except (ValueError, TypeError):
                raise ValidationError(_("Invalid food entry."))
        else:
            pk = None
        cleaned.append({"id": pk, "name": name, "reaction": reaction})
    return cleaned


def validate_meal_foods(feeding, rows, user):
    existing = {food.pk: food for food in feeding.foods.all()} if feeding.pk else {}
    ids = [row["id"] for row in rows if row["id"]]
    if len(ids) != len(set(ids)) or set(ids) - set(existing):
        raise ValidationError(_("A food entry does not belong to this meal."))
    if rows and "solid food" not in (feeding.type, feeding.secondary_type):
        raise ValidationError(_("Choose Solid food to record foods in this meal."))
    changes = []
    for row in rows:
        old = existing.get(row["id"])
        if old is None:
            changes.append("add")
        elif old.name != row["name"] or (old.reaction or "") != row["reaction"]:
            changes.append("change")
    if set(existing) - set(ids):
        changes.append("delete")
    if any(not user or not user.has_perm(f"core.{action}_food") for action in changes):
        raise PermissionDenied(
            _("You do not have permission to make these food changes.")
        )


def save_meal_foods(feeding, rows, user):
    # Called within the same transaction as the feeding, including API replay.
    validate_meal_foods(feeding, rows, user)
    keep = []
    for row in rows:
        if row["id"]:
            food = feeding.foods.get(pk=row["id"])
            food.name, food.reaction = row["name"], row["reaction"]
        else:
            food = Food(
                feeding=feeding,
                name=row["name"],
                reaction=row["reaction"],
                created_by=user,
            )
        food.child_id, food.time = feeding.child_id, feeding.start
        food.save()
        keep.append(food.pk)
    feeding.foods.exclude(pk__in=keep).delete()


def food_suggestions(user):
    if not user or not user.has_perm("core.view_food"):
        return []
    return list(
        scoped(Food.objects.all(), user)
        .order_by("name")
        .values_list("name", flat=True)
        .distinct()[:200]
    )
