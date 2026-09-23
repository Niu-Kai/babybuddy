"""Offline entry replay with permission rechecks and transactional deduplication."""

import hashlib
import json
import uuid
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.http import QueryDict
from django.urls import reverse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from core import models, utils
from core.access import scoped, can_access
from core.units import convert, SPECS, preferred_unit, entry_value
from babybuddy.models import OfflineReceipt
from api import serializers

REGISTRY = {
    "medication": (
        models.Medication,
        serializers.MedicationSerializer,
        "Medication",
        [
            ("name", "Medication", "text"),
            ("dosage", "Dose", "number"),
            ("dosage_unit", "Dose unit", "choice"),
        ],
    ),
    "feeding": (
        models.Feeding,
        serializers.FeedingSerializer,
        "Feeding",
        [
            ("type", "Type", "choice"),
            ("method", "Method", "choice"),
            ("amount", "Amount", "number"),
        ],
    ),
    "diaperchange": (
        models.DiaperChange,
        serializers.DiaperChangeSerializer,
        "Diaper change",
        [("wet", "Wet", "boolean"), ("solid", "Solid", "boolean")],
    ),
    "sleep": (
        models.Sleep,
        serializers.SleepSerializer,
        "Sleep",
        [("nap", "Nap", "boolean")],
    ),
    "pumping": (
        models.Pumping,
        serializers.PumpingSerializer,
        "Pumping",
        [("amount", "Amount", "number"), ("side", "Side", "choice")],
    ),
    "weight": (
        models.Weight,
        serializers.WeightSerializer,
        "Weight",
        [("weight", "Weight", "number")],
    ),
    "height": (
        models.Height,
        serializers.HeightSerializer,
        "Height",
        [("height", "Height", "number")],
    ),
    "headcircumference": (
        models.HeadCircumference,
        serializers.HeadCircumferenceSerializer,
        "Head circumference",
        [("head_circumference", "Head circumference", "number")],
    ),
    "temperature": (
        models.Temperature,
        serializers.TemperatureSerializer,
        "Temperature",
        [("temperature", "Temperature", "number")],
    ),
    "tummytime": (models.TummyTime, serializers.TummyTimeSerializer, "Tummy time", []),
    "bathtime": (models.BathTime, serializers.BathTimeSerializer, "Bath", []),
    "reflux": (
        models.Reflux,
        serializers.RefluxSerializer,
        "Reflux",
        [("severity", "Severity", "choice")],
    ),
    "food": (
        models.Food,
        serializers.FoodSerializer,
        "Food",
        [("name", "Food", "text"), ("reaction", "Reaction", "choice")],
    ),
    "customactivity": (
        models.CustomActivity,
        serializers.CustomActivitySerializer,
        "Custom activity",
        [],
    ),
    "note": (
        models.Note,
        serializers.NoteSerializer,
        "Note",
        [("note", "Note", "text")],
    ),
}


def recent_history(user):
    """A bounded, read-only snapshot; recheck view and child access each refresh."""
    now = timezone.now()
    cutoff = now - timedelta(days=7)
    history = []
    view_children = user.has_perm("core.view_child")
    for key, (model, serializer, label, fields) in REGISTRY.items():
        if not user.has_perm(f"core.view_{key}") or (
            key != "pumping" and not view_children
        ):
            continue
        names = {field.name for field in model._meta.fields}
        stamp = "start" if "start" in names else "time" if "time" in names else "date"
        date_only = stamp == "date"
        queryset = (
            scoped(model.objects.all(), user)
            .filter(
                **{
                    stamp + "__gte": cutoff.date() if date_only else cutoff,
                    stamp + "__lte": now.date() if date_only else now,
                }
            )
            .order_by("-" + stamp, "-pk")
        )
        if key != "pumping":
            queryset = queryset.select_related("child")
        if key == "customactivity":
            queryset = queryset.select_related("activity_type")
        for entry in queryset[:200]:
            details = []
            for name, title, kind in fields:
                value = getattr(entry, name)
                if value in (None, "") or value is False:
                    continue
                if kind == "boolean":
                    details.append(str(model._meta.get_field(name).verbose_name))
                elif key in SPECS and name in SPECS[key][0]:
                    details.append(entry_value(entry, name))
                elif kind == "choice":
                    details.append(str(getattr(entry, "get_" + name + "_display")()))
                else:
                    details.append(str(value)[:300])
            if key == "feeding":
                from core.top_ups import top_up_summary

                if entry.secondary_type:
                    details.append(
                        str(entry.get_secondary_type_display())
                        + ": "
                        + entry_value(entry, "secondary_amount")
                    )
                if entry.top_up_at:
                    details.append(top_up_summary(entry))
            if getattr(entry, "duration", None) is not None:
                details.append(utils.duration_string(entry.duration, precision="m"))
            at = getattr(entry, stamp)
            history.append(
                {
                    "key": f"{key}:{entry.pk}",
                    "label": (
                        entry.activity_type.name
                        if key == "customactivity"
                        else str(model._meta.verbose_name)
                    ),
                    "child": str(entry.child) if key != "pumping" else "",
                    "at": at.isoformat(),
                    "details": " · ".join(details),
                }
            )
    return sorted(history, key=lambda item: (item["at"], item["key"]), reverse=True)[
        :200
    ]


class OfflineContext(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        activities = []
        for key, (model, serializer, label, fields) in REGISTRY.items():
            if not request.user.has_perm(f"core.add_{key}"):
                continue
            if key == "customactivity":
                for definition in models.ActivityType.objects.filter(archived=False):
                    custom_fields = []
                    for name, label, kind in (
                        ("amount", definition.amount_label, "number"),
                        ("choice", definition.choice_label, "choice"),
                        ("checked", definition.check_label, "boolean"),
                        ("text", definition.text_label, "text"),
                        ("notes", "Notes", "text"),
                    ):
                        if label:
                            custom_fields.append(
                                {
                                    "name": name,
                                    "label": label
                                    + (
                                        " (" + definition.amount_unit + ")"
                                        if name == "amount" and definition.amount_unit
                                        else ""
                                    ),
                                    "kind": kind,
                                    "required": False,
                                    "choices": (
                                        [(v, v) for v in definition.options()]
                                        if name == "choice"
                                        else []
                                    ),
                                }
                            )
                    activities.append(
                        {
                            "key": f"customactivity:{definition.pk}",
                            "activity_type": definition.pk,
                            "add_url": reverse("core:customactivity-add")
                            + f"?activity_type={definition.pk}",
                            "label": definition.name,
                            "paired": True,
                            "timer": definition.track_duration,
                            "duration": definition.track_duration,
                            "date_only": False,
                            "fields": custom_fields,
                            "units": [],
                            "unit": "",
                        }
                    )
                continue
            names = {field.name for field in model._meta.fields}
            activities.append(
                {
                    "key": key,
                    "add_url": reverse(
                        "core:"
                        + ("head-circumference" if key == "headcircumference" else key)
                        + "-add"
                    ),
                    "label": label,
                    "paired": "end" in names,
                    "timer": "end" in names,
                    "duration": "end" in names,
                    "date_only": "date" in names,
                    "fields": [
                        {
                            "name": name,
                            "label": title,
                            "kind": kind,
                            "required": not model._meta.get_field(name).blank,
                            "choices": list(model._meta.get_field(name).choices or []),
                        }
                        for name, title, kind in fields
                    ],
                    "units": list(SPECS[key][3]) if key in SPECS else [],
                    "unit": (
                        preferred_unit(request.user.settings, key)
                        if key in SPECS
                        else ""
                    ),
                }
            )
        children = (
            [
                {"id": c.pk, "name": str(c), "slug": c.slug}
                for c in scoped(models.Child.objects.all(), request.user)
            ]
            if request.user.has_perm("core.view_child")
            else []
        )
        return Response(
            {
                "user": request.user.pk,
                "username": request.user.get_username(),
                "children": children,
                "selected_child": request.session.get("child_scope", "all"),
                "activities": activities,
                "csrf": get_token(request),
                "history": recent_history(request.user),
                "use_24_hour_time": request.user.settings.use_24_hour_time,
            },
            headers={"Cache-Control": "private, no-store"},
        )


def queued_form(key, payload, user):
    """Replay normal entry fields through the same ModelForm as the website."""
    from core import forms
    from core.feature_preferences import apply_fields

    fields = payload.get("fields")
    if not isinstance(fields, dict) or len(fields) > 100:
        raise ValidationError("Invalid form data.")
    data = QueryDict(mutable=True)
    for name, values in fields.items():
        if name in {"csrfmiddlewaretoken", "password", "api_key"}:
            raise ValidationError("Credentials must not be stored in an entry.")
        if (
            not isinstance(name, str)
            or not isinstance(values, list)
            or len(values) > 100
            or any(not isinstance(v, str) or len(v) > 10000 for v in values)
        ):
            raise ValidationError("Invalid form field.")
        data.setlist(name, values)
    if key != "pumping":
        try:
            child_id = int(data.get("child", ""))
        except (ValueError, TypeError):
            raise ValidationError({"child": "Choose a child."})
        if not can_access(user, child_id):
            raise PermissionDenied("This child is not allowed for your account.")
    if key == "customactivity":
        from core.custom_activities import CustomActivityForm

        form_class = CustomActivityForm
    else:
        form_class = getattr(forms, REGISTRY[key][0].__name__ + "Form")
    timer = payload.get("timer")
    if timer is not None and (
        not isinstance(timer, int) or isinstance(timer, bool) or timer <= 0
    ):
        raise ValidationError("Invalid timer.")
    form = form_class(data=data, user=user, **({"timer": timer} if timer else {}))
    apply_fields(form)
    if not form.is_valid():
        errors = {
            key: [str(message) for message in values]
            for key, values in form.errors.items()
        }
        if form.overlap_conflict:
            errors["allow_overlap"] = [str(form.fields["allow_overlap"].label)]
        raise ValidationError(errors)
    form.instance._inventory_actor_id = user.pk
    try:
        return form.save()
    except DjangoValidationError as error:
        raise ValidationError(
            error.message_dict if hasattr(error, "message_dict") else error.messages
        )


class OfflineSync(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        if data.get("user") != request.user.pk:
            raise PermissionDenied(
                "Sign in to the account that created this offline entry."
            )
        original_key = data.get("activity")
        key = original_key
        definition_id = None
        if isinstance(key, str) and key.startswith("customactivity:"):
            try:
                definition_id = int(key.split(":", 1)[1])
            except ValueError:
                raise ValidationError("Invalid activity type.")
            key = "customactivity"
        if key not in REGISTRY or not request.user.has_perm(f"core.add_{key}"):
            raise PermissionDenied("This activity is not allowed for your account.")
        try:
            client_key = uuid.UUID(str(data.get("key")))
        except (ValueError, TypeError):
            raise ValidationError("Invalid entry identifier.")
        payload = data.get("entry")
        if not isinstance(payload, dict) or len(json.dumps(payload)) > 20000:
            raise ValidationError("Invalid entry data.")
        form_mode = data.get("format") == "form"
        if form_mode and not isinstance(payload.get("fields"), dict):
            raise ValidationError("Invalid form data.")
        if data.get("format") not in (None, "form"):
            raise ValidationError("Invalid entry format.")
        if (
            key != "pumping"
            and not form_mode
            and not can_access(request.user, payload.get("child"))
        ):
            raise PermissionDenied("This child is not allowed for your account.")
        if key == "customactivity":
            activity_type = payload.get("activity_type")
            if form_mode:
                values = payload.get("fields", {}).get("activity_type", [])
                try:
                    activity_type = int(values[-1])
                except (ValueError, TypeError, IndexError):
                    activity_type = None
            if not definition_id or activity_type != definition_id:
                raise ValidationError("Choose the matching activity type.")
            if not models.ActivityType.objects.filter(
                pk=definition_id, archived=False
            ).exists():
                raise ValidationError(
                    "This activity type is no longer available. Your entry remains on this device."
                )
        digest = hashlib.sha256(
            json.dumps(
                {
                    "activity": original_key,
                    "entry": payload,
                    "unit": data.get("unit"),
                    **({"format": "form"} if form_mode else {}),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with transaction.atomic():
            receipt, created = OfflineReceipt.objects.get_or_create(
                user=request.user, key=client_key, defaults={"digest": digest}
            )
            if not created:
                if receipt.digest != digest:
                    raise ValidationError(
                        "This entry identifier was already used for different data."
                    )
                return Response({**receipt.result, "duplicate": True})
            if form_mode:
                try:
                    zone = ZoneInfo(payload.get("timezone", ""))
                except (ZoneInfoNotFoundError, ValueError, TypeError):
                    raise ValidationError("Invalid entry timezone.")
                with timezone.override(zone):
                    instance = queued_form(key, payload, request.user)
                receipt.result = {"id": instance.pk, "activity": original_key}
                receipt.save(update_fields=["result"])
                return Response(receipt.result, status=201)
            values = payload.copy()
            unit = data.get("unit")
            if key == "feeding" and "solid food" in {
                values.get("type"),
                values.get("secondary_type"),
            }:
                raise ValidationError(
                    {
                        "type": "Use the Food activity for solid food; liquid units do not apply."
                    }
                )
            if key in SPECS:
                fields, canonical, _, choices = SPECS[key]
                if unit not in dict(choices):
                    raise ValidationError({"unit": "Choose a valid unit."})
                for field in fields:
                    if values.get(field) is not None:
                        try:
                            values[field] = convert(values[field], unit, canonical)
                        except (TypeError, ValueError, ArithmeticError):
                            raise ValidationError({field: "Enter a valid number."})
            _, serializer_class, _, _ = REGISTRY[key]
            serializer = serializer_class(data=values, context={"request": request})
            try:
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(
                    **({"entry_unit": unit} if key in SPECS else {})
                )
            except DjangoValidationError as error:
                raise ValidationError(
                    error.message_dict
                    if hasattr(error, "message_dict")
                    else error.messages
                )
            receipt.result = {"id": instance.pk, "activity": original_key}
            receipt.save(update_fields=["result"])
        return Response(receipt.result, status=201)
