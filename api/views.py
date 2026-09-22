# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.schemas.openapi import AutoSchema

from core import models
from babybuddy import models as babybuddy_models

from . import serializers, filters


class RelatedDataMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        fields = {field.name for field in queryset.model._meta.get_fields()}
        if "created_by" in fields:
            queryset = queryset.select_related("created_by")
        if "tags" in fields and self.action in {"list", "retrieve"}:
            queryset = queryset.prefetch_related("tags")
        return queryset


class BMIViewSet(RelatedDataMixin, viewsets.ReadOnlyModelViewSet):
    queryset = models.BMI.objects.filter(
        source_weight__isnull=False, source_height__isnull=False
    )
    serializer_class = serializers.BMISerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("child", "date")
    ordering = "-date"

    def get_view_name(self):
        """
        Gets the view name without changing the case of the model verbose name.
        """
        name = models.BMI._meta.verbose_name
        if self.suffix:
            name += " " + self.suffix
        return name


class ChildViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Child.objects.all()
    serializer_class = serializers.ChildSerializer
    lookup_field = "slug"
    filterset_fields = (
        "id",
        "first_name",
        "last_name",
        "slug",
        "birth_date",
        "birth_time",
    )
    ordering_fields = ("birth_date", "birth_time", "first_name", "last_name", "slug")
    ordering = ["-birth_date", "-birth_time"]


class DiaperChangeViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.DiaperChange.objects.all()
    serializer_class = serializers.DiaperChangeSerializer
    filterset_class = filters.DiaperChangeFilter
    ordering_fields = ("amount", "time")
    ordering = "-time"

    def perform_update(self, serializer):
        serializer.instance._inventory_actor_id = self.request.user.pk
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        instance._inventory_actor_id = self.request.user.pk
        super().perform_destroy(instance)


class FeedingViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Feeding.objects.all()
    serializer_class = serializers.FeedingSerializer
    filterset_class = filters.FeedingFilter
    ordering_fields = ("amount", "duration", "end", "start")
    ordering = "-end"


class HeadCircumferenceViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.HeadCircumference.objects.all()
    serializer_class = serializers.HeadCircumferenceSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "head_circumference")
    ordering = "-date"


class HeightViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Height.objects.all()
    serializer_class = serializers.HeightSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "height")
    ordering = "-date"


class MedicationViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Medication.objects.all()
    serializer_class = serializers.MedicationSerializer
    filterset_class = filters.MedicationFilter
    ordering_fields = ("time", "name", "dosage")
    ordering = "-time"

    def get_view_name(self):
        # Use model's verbose_name for consistency with user-facing strings
        name = self.queryset.model._meta.verbose_name
        suffix = getattr(self, "suffix", None)
        if suffix:
            name = f"{name} {suffix}"
        return name


class AppointmentViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Appointment.objects.all()
    serializer_class = serializers.AppointmentSerializer
    filterset_class = filters.AppointmentFilter
    ordering_fields = ("start", "end")
    ordering = "start"


class NoteViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Note.objects.all()
    serializer_class = serializers.NoteSerializer
    filterset_class = filters.NoteFilter
    ordering_fields = "time"
    ordering = "-time"


class PumpingViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Pumping.objects.all()
    serializer_class = serializers.PumpingSerializer
    filterset_class = filters.PumpingFilter
    ordering_fields = ("amount", "duration", "end", "start")
    ordering = "-end"


class SleepViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Sleep.objects.all()
    serializer_class = serializers.SleepSerializer
    filterset_class = filters.SleepFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-end"


class TagViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Tag.objects.all()
    serializer_class = serializers.TagSerializer
    lookup_field = "slug"
    filterset_fields = ("last_used", "name")
    ordering_fields = ("last_used", "name", "slug")
    ordering = "name"


class TemperatureViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Temperature.objects.all()
    serializer_class = serializers.TemperatureSerializer
    filterset_class = filters.TemperatureFilter
    ordering_fields = ("temperature", "time")
    ordering = "-time"


class TimerViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Timer.objects.all()
    serializer_class = serializers.TimerSerializer
    filterset_class = filters.TimerFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-start"

    @action(detail=True, methods=["patch"])
    def restart(self, request, pk=None):
        timer = self.get_object()
        timer.restart()
        return Response(self.serializer_class(timer).data)

    @action(detail=True, methods=["patch"])
    def pause(self, request, pk=None):
        timer = self.get_object()
        timer.pause()
        return Response(self.serializer_class(timer).data)

    @action(detail=True, methods=["patch"])
    def resume(self, request, pk=None):
        timer = self.get_object()
        timer.resume()
        return Response(self.serializer_class(timer).data)


class TummyTimeViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.TummyTime.objects.all()
    serializer_class = serializers.TummyTimeSerializer
    filterset_class = filters.TummyTimeFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-start"


class WeightViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Weight.objects.all()
    serializer_class = serializers.WeightSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "weight")
    ordering = "-date"


class ProfileView(views.APIView):
    schema = AutoSchema(operation_id_base="CurrentProfile")

    action = "get"
    basename = "profile"

    queryset = babybuddy_models.Settings.objects.all()
    serializer_class = serializers.ProfileSerializer

    def get(self, request):
        settings = get_object_or_404(
            babybuddy_models.Settings.objects, user=request.user
        )
        serializer = self.serializer_class(settings)
        return Response(serializer.data)


class BathTimeViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.BathTime.objects.all()
    serializer_class = serializers.BathTimeSerializer
    filterset_class = filters.BathTimeFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-start"


class RefluxViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Reflux.objects.all()
    serializer_class = serializers.RefluxSerializer
    filterset_class = filters.RefluxFilter
    ordering_fields = ("time",)
    ordering = "-time"


class FoodViewSet(RelatedDataMixin, viewsets.ModelViewSet):
    queryset = models.Food.objects.all()
    serializer_class = serializers.FoodSerializer
    filterset_class = filters.FoodFilter
    ordering_fields = ("time",)
    ordering = "-time"
