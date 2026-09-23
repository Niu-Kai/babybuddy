"""Authenticated, bounded read APIs for integrations. No arbitrary ORM paths."""

import json
from django.db.models import Sum
from django.http import QueryDict
from django.utils import timezone
from django_filters.filterset import filterset_factory
from rest_framework import serializers as drf, views
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from core import models
from core.access import scoped
from inventory.models import StockItem
from . import views as endpoints


class IntegrationThrottle(UserRateThrottle):
    scope = "integration_reads"
    rate = "60/min"


class SettingsView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {
            "timezone": timezone.get_current_timezone_name(),
            "server_time": timezone.now().isoformat(),
        }
        if request.user.has_perm("core.view_sleep"):
            data["sleep"] = {
                "nap_start_min": models.Sleep.settings.nap_start_min.isoformat(),
                "nap_start_max": models.Sleep.settings.nap_start_max.isoformat(),
            }
        if request.user.has_perm("core.view_child"):
            data["dashboard"] = {
                "day_start": models.Child.settings.day_start.isoformat()
            }
        if request.user.has_perm("core.view_feeding"):
            data["feeding"] = {
                "interval_from_end": models.Feeding.settings.feeding_diff_end
            }
        return Response(data)


class StockSerializer(drf.ModelSerializer):
    class Meta:
        model = StockItem
        fields = (
            "id",
            "name",
            "category",
            "size",
            "stage",
            "unit",
            "quantity",
            "archived",
        )


class StockEndpoint:
    queryset = StockItem.objects.all()
    serializer_class = StockSerializer
    filterset_fields = ("id", "category", "size", "stage", "archived")
    ordering_fields = ("id", "name", "quantity")
    ordering = ("name", "pk")


RESOURCES = {
    "children": endpoints.ChildViewSet,
    "feedings": endpoints.FeedingViewSet,
    "sleep": endpoints.SleepViewSet,
    "changes": endpoints.DiaperChangeViewSet,
    "pumping": endpoints.PumpingViewSet,
    "food": endpoints.FoodViewSet,
    "notes": endpoints.NoteViewSet,
    "timers": endpoints.TimerViewSet,
    "weight": endpoints.WeightViewSet,
    "height": endpoints.HeightViewSet,
    "head-circumference": endpoints.HeadCircumferenceViewSet,
    "bmi": endpoints.BMIViewSet,
    "temperature": endpoints.TemperatureViewSet,
    "medication": endpoints.MedicationViewSet,
    "bath-times": endpoints.BathTimeViewSet,
    "tummy-times": endpoints.TummyTimeViewSet,
    "reflux": endpoints.RefluxViewSet,
    "appointments": endpoints.AppointmentViewSet,
    "custom-activities": endpoints.CustomActivityViewSet,
    "inventory": StockEndpoint,
}
# Only durations have an unambiguous aggregate unit across legacy records.
SUM_FIELDS = {
    name: {"duration": "seconds"}
    for name in ("sleep", "feedings", "pumping", "bath-times", "tummy-times")
}


class QuerySpec(drf.Serializer):
    key = drf.RegexField(r"^[a-zA-Z][a-zA-Z0-9_]{0,39}$")
    resource = drf.ChoiceField(choices=list(RESOURCES))
    filters = drf.DictField(default=dict)
    fields = drf.ListField(
        child=drf.CharField(max_length=50), required=False, min_length=1, max_length=30
    )
    order_by = drf.CharField(max_length=64, required=False)
    limit = drf.IntegerField(default=10, min_value=1, max_value=50)
    offset = drf.IntegerField(default=0, min_value=0, max_value=10000)
    operation = drf.ChoiceField(choices=("list", "count", "sum"), default="list")
    metric = drf.CharField(max_length=30, required=False)

    def validate_filters(self, value):
        if len(value) > 16 or any(
            not isinstance(item, (str, int, float, bool)) or len(str(item)) > 256
            for item in value.values()
        ):
            raise ValidationError(
                "Use up to 16 scalar filters, each at most 256 characters."
            )
        return {
            key: str(item).lower() if isinstance(item, bool) else str(item)
            for key, item in value.items()
        }

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise ValidationError("Unknown query option.")
        return super().to_internal_value(data)


class QueryView(views.APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [IntegrationThrottle]

    def get(self, request):
        catalog = {}
        for name, endpoint in RESOURCES.items():
            model = endpoint.queryset.model
            if not request.user.has_perm(
                f"{model._meta.app_label}.view_{model._meta.model_name}"
            ):
                continue
            filter_class = getattr(
                endpoint, "filterset_class", None
            ) or filterset_factory(model, fields=endpoint.filterset_fields)
            serializer = endpoint.serializer_class(context={"request": request})
            catalog[name] = {
                "filters": list(filter_class.base_filters),
                "fields": [
                    key
                    for key, field in serializer.fields.items()
                    if not field.write_only
                ],
                "ordering": (
                    list(getattr(endpoint, "ordering_fields", ("id",)))
                    if not isinstance(
                        getattr(endpoint, "ordering_fields", ("id",)), str
                    )
                    else [endpoint.ordering_fields]
                ),
                "sum_metrics": SUM_FIELDS.get(name, {}),
            }
        return Response(
            {"resources": catalog, "max_queries": 10, "max_rows_per_query": 50}
        )

    def post(self, request):
        if (
            not isinstance(request.data, dict)
            or set(request.data) != {"queries"}
            or len(json.dumps(request.data)) > 20000
        ):
            raise ValidationError("Provide a queries array (maximum 20 KB).")
        queries = request.data["queries"]
        if not isinstance(queries, list) or not 1 <= len(queries) <= 10:
            raise ValidationError("Provide between 1 and 10 queries.")
        specs = QuerySpec(data=queries, many=True)
        specs.is_valid(raise_exception=True)
        keys = [item["key"] for item in specs.validated_data]
        if len(set(keys)) != len(keys):
            raise ValidationError("Query keys must be unique.")
        return Response(
            {
                "results": {
                    spec["key"]: self.execute(spec, request)
                    for spec in specs.validated_data
                }
            }
        )

    def execute(self, spec, request):
        endpoint = RESOURCES[spec["resource"]]
        model = endpoint.queryset.model
        if not request.user.has_perm(
            f"{model._meta.app_label}.view_{model._meta.model_name}"
        ):
            raise PermissionDenied("You cannot read this resource.")
        queryset = scoped(endpoint.queryset.all(), request.user)
        filter_class = getattr(endpoint, "filterset_class", None) or filterset_factory(
            model, fields=endpoint.filterset_fields
        )
        if set(spec["filters"]) - set(filter_class.base_filters):
            raise ValidationError({spec["key"]: "Unknown filter. See GET /api/query."})
        params = QueryDict(mutable=True)
        params.update(spec["filters"])
        filters = filter_class(data=params, queryset=queryset, request=request)
        if not filters.is_valid():
            raise ValidationError({spec["key"]: filters.errors})
        queryset = filters.qs.distinct()
        available = endpoint.serializer_class(context={"request": request}).fields
        readable = {key for key, field in available.items() if not field.write_only}
        if "fields" in spec and set(spec["fields"]) - readable:
            raise ValidationError({spec["key"]: "Unknown or unavailable output field."})
        if spec["operation"] == "count":
            return {"count": queryset.count()}
        if spec["operation"] == "sum":
            metric = spec.get("metric")
            if metric not in SUM_FIELDS.get(spec["resource"], {}):
                raise ValidationError(
                    {spec["key"]: "Unsupported sum metric. See GET /api/query."}
                )
            value = queryset.aggregate(value=Sum(metric))["value"]
            return {
                "value": value.total_seconds() if value is not None else 0,
                "unit": "seconds",
            }
        ordering = spec.get("order_by")
        allowed = getattr(endpoint, "ordering_fields", ("id",))
        allowed = (allowed,) if isinstance(allowed, str) else allowed
        if ordering and ordering.lstrip("-") not in allowed:
            raise ValidationError({spec["key"]: "Unsupported ordering."})
        default_order = (
            getattr(endpoint, "ordering", None) or model._meta.ordering or ("pk",)
        )
        default_order = (
            (default_order,) if isinstance(default_order, str) else default_order
        )
        queryset = queryset.order_by(*((ordering, "pk") if ordering else default_order))
        model_fields = {field.name for field in model._meta.get_fields()}
        if "created_by" in model_fields:
            queryset = queryset.select_related("created_by")
        if "tags" in model_fields:
            queryset = queryset.prefetch_related("tags")
        if model is models.Feeding:
            queryset = queryset.prefetch_related("foods")
        rows = list(queryset[spec["offset"] : spec["offset"] + spec["limit"] + 1])
        serializer = endpoint.serializer_class(
            rows[: spec["limit"]], many=True, context={"request": request}
        )
        data = serializer.data
        if "fields" in spec:
            data = [
                {key: value for key, value in row.items() if key in spec["fields"]}
                for row in data
            ]
        return {
            "items": data,
            "next_offset": (
                spec["offset"] + spec["limit"] if len(rows) > spec["limit"] else None
            ),
        }
