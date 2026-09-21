# -*- coding: utf-8 -*-
from core import models
import django_filters
from django_filters import rest_framework as filters


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class ChildFieldFilter(filters.FilterSet):
    class Meta:
        abstract = True
        fields = ["child"]


class TagsFieldFilter(filters.FilterSet):
    tags = CharInFilter(
        field_name="tags__name",
        label="tag",
        help_text="A list of tag names, comma separated",
    )

    class Meta:
        abstract = True


class TimeFieldFilter(ChildFieldFilter):
    date = filters.IsoDateTimeFilter(field_name="time", label="DateTime")
    date_max = filters.IsoDateTimeFilter(
        field_name="time", label="Max. DateTime", lookup_expr="lte"
    )
    date_min = filters.IsoDateTimeFilter(
        field_name="time", label="Min. DateTime", lookup_expr="gte"
    )

    class Meta:
        abstract = True
        fields = sorted(ChildFieldFilter.Meta.fields + ["date", "date_max", "date_min"])


class StartEndFieldFilter(ChildFieldFilter):
    end = filters.IsoDateTimeFilter(field_name="end", label="End DateTime")
    end_max = filters.IsoDateTimeFilter(
        field_name="end", label="Max. End DateTime", lookup_expr="lte"
    )
    end_min = filters.IsoDateTimeFilter(
        field_name="end", label="Min. End DateTime", lookup_expr="gte"
    )
    start = filters.IsoDateTimeFilter(field_name="start", label="Start DateTime")
    start_max = filters.IsoDateTimeFilter(
        field_name="start", lookup_expr="lte", label="Max. End DateTime"
    )
    start_min = filters.IsoDateTimeFilter(
        field_name="start", lookup_expr="gte", label="Min. Start DateTime"
    )

    class Meta:
        abstract = True
        fields = sorted(
            ChildFieldFilter.Meta.fields
            + ["end", "end_max", "end_min", "start", "start_max", "start_min"]
        )


class DiaperChangeFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.DiaperChange
        fields = sorted(
            TimeFieldFilter.Meta.fields + ["wet", "solid", "color", "amount"]
        )


class FeedingFilter(StartEndFieldFilter, TagsFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.Feeding
        fields = sorted(StartEndFieldFilter.Meta.fields + ["type", "method"])


class MedicationFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.Medication
        fields = sorted(TimeFieldFilter.Meta.fields + ["name", "dosage_unit"])


class AppointmentFilter(StartEndFieldFilter, TagsFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.Appointment


class NoteFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.Note


class PumpingFilter(StartEndFieldFilter):
    side = filters.CharFilter(field_name="side", label="Side")

    class Meta(StartEndFieldFilter.Meta):
        model = models.Pumping


class SleepFilter(StartEndFieldFilter, TagsFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.Sleep


class TemperatureFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.Temperature


class TimerFilter(StartEndFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.Timer
        fields = sorted(StartEndFieldFilter.Meta.fields + ["name", "user"])


class TummyTimeFilter(StartEndFieldFilter, TagsFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.TummyTime


class DjangoFilterBackend(django_filters.rest_framework.DjangoFilterBackend):
    """
    django-filter 25 dropped the schema hooks Django REST framework's built-in
    OpenAPI generator still calls, so `/api/schema` (and `generateschema`)
    raised `AttributeError`. This restores the query parameter listing.
    """

    def get_schema_operation_parameters(self, view):
        queryset = getattr(view, "queryset", None)
        if queryset is None:
            try:
                queryset = view.get_queryset()
            except Exception:
                return []
        filterset_class = self.get_filterset_class(view, queryset)
        if filterset_class is None:
            return []

        parameters = []
        for field_name, field in filterset_class.base_filters.items():
            label = field.label if field.label is not None else field_name
            parameters.append(
                {
                    "name": field_name,
                    "required": field.extra.get("required", False),
                    "in": "query",
                    "description": str(label),
                    "schema": {"type": "string"},
                }
            )
        return parameters


class BathTimeFilter(StartEndFieldFilter, TagsFieldFilter):
    class Meta(StartEndFieldFilter.Meta):
        model = models.BathTime


class RefluxFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.Reflux


class FoodFilter(TimeFieldFilter, TagsFieldFilter):
    class Meta(TimeFieldFilter.Meta):
        model = models.Food
