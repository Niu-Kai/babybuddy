# -*- coding: utf-8 -*-
from copy import deepcopy
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from taggit.serializers import TagListSerializerField, TaggitSerializer

from core import models
from babybuddy import models as babybuddy_models


class CoreModelSerializer(serializers.HyperlinkedModelSerializer):
    """
    Provide the child link (used by most core models) and run model clean()
    methods during POST operations.
    """

    child = serializers.PrimaryKeyRelatedField(queryset=models.Child.objects.all())
    created_by = serializers.CharField(
        source="created_by_display", read_only=True, required=False
    )

    def get_fields(self):
        from core.access import scoped

        fields = super().get_fields()
        request = self.context.get("request")
        if request:
            for name in ("child", "timer"):
                field = fields.get(name)
                if field is not None and field.queryset is not None:
                    field.queryset = scoped(field.queryset, request.user)
        return fields

    def create(self, validated_data):
        # Record who added the entry (#900).
        request = self.context.get("request")
        model_fields = {field.name for field in self.Meta.model._meta.get_fields()}
        if "created_by" in model_fields and request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def validate(self, attrs):
        # Ensure that all instance data is available for partial updates to
        # support clean methods that compare multiple fields.
        if self.partial:
            new_instance = deepcopy(self.instance)
            for attr, value in attrs.items():
                setattr(new_instance, attr, value)
        else:
            new_instance = self.Meta.model(**attrs)
        new_instance.clean()
        return attrs


class CoreModelWithDurationSerializer(CoreModelSerializer):
    """
    Specific serializer base for models with a "start" and "end" field.
    """

    child = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        help_text="Required unless a Timer value is provided.",
        queryset=models.Child.objects.all(),
        required=False,
    )

    timer = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        help_text="May be used in place of the Start, End, and/or Child values.",
        queryset=models.Timer.objects.all(),
        required=False,
        write_only=True,
    )

    class Meta:
        abstract = True
        extra_kwargs = {
            "start": {
                "help_text": "Required unless a Timer value is provided.",
                "required": False,
            },
            "end": {
                "help_text": "Required unless a Timer value is provided.",
                "required": False,
            },
        }

    def validate(self, attrs):
        # Check for a special "timer" data argument that can be used in place
        # of "start" and "end" fields as well as "child" if it is set on the
        # Timer entry.
        timer = None
        if "timer" in attrs:
            # Remove the "timer" attribute (super validation would fail as it
            # is not a true field on the model).
            timer = attrs.pop("timer")
            if timer is None:
                raise ValidationError({"timer": "This field may not be null."})
            if not timer.can_be_consumed_by(self.context["request"].user):
                raise PermissionDenied("You do not have permission to consume timers.")

            if timer.child and self.Meta.model is not models.Pumping:
                attrs["child"] = timer.child

            if timer.context.get("activity") == self.Meta.model._meta.model_name:
                for key in ("type", "method"):
                    if key in timer.context:
                        attrs.setdefault(key, timer.context[key])
            # Overwrites values provided directly!
            attrs["start"] = timer.start
            attrs["end"] = timer.start + timer.duration()

        # The "child", "start", and "end" field should all be set at this
        # point. If one is not, model validation will fail because they are
        # required fields at the model level.
        if not self.partial:
            errors = {}
            for field in (
                ["start", "end"]
                if self.Meta.model is models.Pumping
                else ["child", "start", "end"]
            ):
                if field not in attrs or not attrs[field]:
                    errors[field] = "This field is required."
            if len(errors) > 0:
                raise ValidationError(errors)

        if self.Meta.model is models.Feeding:
            for field in ("type", "method"):
                if not attrs.get(field, getattr(self.instance, field, None)):
                    raise ValidationError({field: "This field is required."})
        attrs = super().validate(attrs)

        self.timer = timer
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        timer = getattr(self, "timer", None)
        if timer is not None:
            try:
                timer = models.Timer.objects.select_for_update().get(pk=timer.pk)
            except models.Timer.DoesNotExist:
                raise ValidationError({"timer": "This timer no longer exists."})
            # The timer may have changed owner since validation.
            if not timer.can_be_consumed_by(self.context["request"].user):
                raise PermissionDenied("You do not have permission to consume timers.")
        instance = super().save(**kwargs)
        if timer is not None:
            timer.stop()
        return instance


class TaggableSerializer(TaggitSerializer, serializers.HyperlinkedModelSerializer):
    tags = TagListSerializerField(required=False)

    def validate_tags(self, tags):
        current = self.instance.tags.names() if self.instance else ()
        models.Tag.check_assignment_permissions(
            self.context["request"].user, tags, current
        )
        return tags


class BMISerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.BMI
        fields = ("created_by", "id", "child", "bmi", "date", "notes", "tags")
        extra_kwargs = {
            "core.BMI.bmi": {"label": "BMI"},
        }


class PumpingSerializer(CoreModelWithDurationSerializer, TaggableSerializer):
    # Retained for older API clients; new sessions belong to the household.
    child = serializers.PrimaryKeyRelatedField(read_only=True)

    amount = serializers.FloatField(required=False)

    def validate(self, attrs):
        from copy import copy
        from core.pumping import set_pumping_total

        entry = copy(self.instance) if self.instance else models.Pumping(amount=None)
        for name in ("amount", "left_amount", "right_amount"):
            if name in attrs:
                setattr(entry, name, attrs[name])
        if (
            self.instance
            and "amount" in attrs
            and not {"left_amount", "right_amount"}.intersection(attrs)
        ):
            entry.left_amount = entry.right_amount = None
            attrs.update(left_amount=None, right_amount=None)
        set_pumping_total(entry)
        attrs["amount"] = entry.amount
        if entry.left_amount is not None or entry.right_amount is not None:
            attrs["side"] = entry.side
        return super().validate(attrs)

    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.Pumping
        fields = (
            "created_by",
            "id",
            "child",
            "amount",
            "left_amount",
            "right_amount",
            "side",
            "start",
            "end",
            "duration",
            "notes",
            "tags",
            "timer",
        )


class ChildSerializer(serializers.HyperlinkedModelSerializer):
    def validate_picture(self, value):
        from core.photos import prepare_photo
        from django.core.exceptions import ValidationError as PhotoError

        try:
            return prepare_photo(value)
        except PhotoError as error:
            raise serializers.ValidationError(error.messages)

    class Meta:
        model = models.Child
        fields = (
            "id",
            "first_name",
            "last_name",
            "birth_date",
            "birth_time",
            "due_date",
            "slug",
            "picture",
        )
        lookup_field = "slug"


class DiaperChangeSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.DiaperChange
        fields = (
            "created_by",
            "id",
            "child",
            "time",
            "wet",
            "solid",
            "color",
            "amount",
            "notes",
            "tags",
        )


class MealFoodListField(serializers.ListField):
    def to_representation(self, value):
        return [
            {"id": food.pk, "name": food.name, "reaction": food.reaction or ""}
            for food in value.all()
        ]


class FeedingSerializer(CoreModelWithDurationSerializer, TaggableSerializer):
    foods = MealFoodListField(
        child=serializers.DictField(), required=False, max_length=20
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and not request.user.has_perm("core.view_food"):
            fields.pop("foods", None)
        return fields

    def validate(self, attrs):
        from copy import copy
        from core.meal_foods import normalize_foods, validate_meal_foods

        from core.top_ups import TOP_UP_FIELDS

        if self.instance and not self.partial:
            for field in TOP_UP_FIELDS:
                attrs.setdefault(field, getattr(self.instance, field))
        supplied = attrs.pop("foods", None)
        attrs = super().validate(attrs)
        meal = copy(self.instance) if self.instance else models.Feeding()
        for key in ("type", "secondary_type"):
            if key in attrs:
                setattr(meal, key, attrs[key])
        if supplied is not None:
            self.meal_foods = normalize_foods(supplied)
            validate_meal_foods(meal, self.meal_foods, self.context["request"].user)
        elif (
            meal.pk
            and meal.foods.exists()
            and "solid food" not in (meal.type, meal.secondary_type)
        ):
            raise ValidationError(
                {
                    "foods": "Remove the foods before changing this meal to a liquid feeding."
                }
            )
        return attrs

    def create(self, validated_data):
        from core.meal_foods import save_meal_foods

        instance = super().create(validated_data)
        if hasattr(self, "meal_foods"):
            save_meal_foods(instance, self.meal_foods, self.context["request"].user)
        return instance

    def update(self, instance, validated_data):
        from core.meal_foods import save_meal_foods

        instance = super().update(instance, validated_data)
        if hasattr(self, "meal_foods"):
            save_meal_foods(instance, self.meal_foods, self.context["request"].user)
        return instance

    type = serializers.ChoiceField(
        choices=models.Feeding._meta.get_field("type").choices, required=False
    )
    method = serializers.ChoiceField(
        choices=models.Feeding._meta.get_field("method").choices, required=False
    )

    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.Feeding
        fields = (
            "top_up_at",
            "top_up_type",
            "top_up_amount",
            "top_up_secondary_type",
            "top_up_secondary_amount",
            "foods",
            "secondary_type",
            "secondary_amount",
            "last_breast",
            "created_by",
            "id",
            "child",
            "start",
            "end",
            "timer",
            "duration",
            "type",
            "method",
            "amount",
            "notes",
            "tags",
        )


class HeadCircumferenceSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.HeadCircumference
        fields = (
            "created_by",
            "id",
            "child",
            "head_circumference",
            "date",
            "notes",
            "tags",
        )


class HeightSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Height
        fields = ("created_by", "id", "child", "height", "date", "notes", "tags")


class MedicationSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Medication
        fields = (
            "created_by",
            "id",
            "child",
            "name",
            "dosage",
            "dosage_unit",
            "time",
            "next_dose_interval",
            "notes",
            "tags",
        )


class AppointmentSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Appointment
        fields = (
            "created_by",
            "id",
            "child",
            "title",
            "start",
            "end",
            "location",
            "notes",
            "tags",
        )


class NoteSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Note
        fields = ("created_by", "id", "child", "note", "image", "time", "tags")


class SleepSerializer(CoreModelWithDurationSerializer, TaggableSerializer):
    nap = serializers.BooleanField(allow_null=True, default=None, required=False)

    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.Sleep
        fields = (
            "created_by",
            "id",
            "child",
            "start",
            "end",
            "timer",
            "duration",
            "nap",
            "notes",
            "tags",
        )


class TagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Tag
        fields = ("slug", "name", "color", "last_used")
        extra_kwargs = {
            "slug": {"required": False, "read_only": True},
            "color": {"required": False},
            "last_used": {"required": False, "read_only": True},
        }


class TemperatureSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Temperature
        fields = ("created_by", "id", "child", "temperature", "time", "notes", "tags")


class TimerSerializer(CoreModelSerializer):
    child = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        allow_empty=True,
        queryset=models.Child.objects.all(),
        required=False,
    )
    user = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        allow_empty=True,
        queryset=get_user_model().objects.all(),
        required=False,
    )
    duration = serializers.DurationField(read_only=True, required=False)
    paused = serializers.BooleanField(read_only=True, source="is_paused")

    class Meta:
        model = models.Timer
        fields = (
            "id",
            "child",
            "name",
            "start",
            "duration",
            "paused",
            "user",
            "context",
        )

    def validate(self, attrs):
        attrs = super(TimerSerializer, self).validate(attrs)
        request_user = self.context["request"].user

        if self.instance is None:
            # Set user to current user if no value is provided.
            if "user" not in attrs or attrs["user"] is None:
                attrs["user"] = request_user
        elif "user" in attrs:
            # The owner may consume the timer, so taking over another user's
            # timer requires the same permission as consuming it.
            attrs["user"] = attrs["user"] or request_user
            if attrs["user"] != self.instance.user and not request_user.has_perm(
                "core.delete_timer"
            ):
                raise PermissionDenied(
                    "You do not have permission to change the user of a timer."
                )

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        # Work on the stored timer, whose owner may have changed since
        # validation, so the check uses it and a stale owner is never saved back.
        instance = models.Timer.objects.select_for_update().get(pk=instance.pk)
        user = validated_data.get("user", instance.user)
        if user != instance.user and not self.context["request"].user.has_perm(
            "core.delete_timer"
        ):
            raise PermissionDenied(
                "You do not have permission to change the user of a timer."
            )
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class TummyTimeSerializer(CoreModelWithDurationSerializer, TaggableSerializer):
    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.TummyTime
        fields = (
            "created_by",
            "id",
            "child",
            "start",
            "end",
            "timer",
            "duration",
            "milestone",
            "notes",
            "tags",
        )


class WeightSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Weight
        fields = (
            "created_by",
            "id",
            "child",
            "weight",
            "date",
            "time",
            "notes",
            "tags",
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
        )
        extra_kwargs = {k: {"read_only": True} for k in fields}


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(many=False)
    api_key = serializers.SerializerMethodField("get_api_key")

    def get_api_key(self, value):
        return self.instance.api_key().key

    class Meta:
        model = babybuddy_models.Settings
        fields = (
            "user",
            "language",
            "timezone",
            "api_key",
        )
        extra_kwargs = {k: {"read_only": True} for k in fields}


class BathTimeSerializer(CoreModelWithDurationSerializer, TaggableSerializer):
    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.BathTime
        fields = (
            "created_by",
            "id",
            "child",
            "start",
            "end",
            "duration",
            "notes",
            "tags",
        )


class RefluxSerializer(CoreModelSerializer, TaggableSerializer):
    class Meta:
        model = models.Reflux
        fields = ("created_by", "id", "child", "time", "severity", "notes", "tags")


class FoodSerializer(CoreModelSerializer, TaggableSerializer):
    feeding = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = models.Food
        fields = (
            "feeding",
            "created_by",
            "id",
            "child",
            "time",
            "name",
            "amount",
            "reaction",
            "notes",
            "tags",
        )


class CustomActivitySerializer(CoreModelWithDurationSerializer):
    activity_type = serializers.PrimaryKeyRelatedField(
        queryset=models.ActivityType.objects.all()
    )

    class Meta(CoreModelWithDurationSerializer.Meta):
        model = models.CustomActivity
        fields = (
            "id",
            "child",
            "activity_type",
            "start",
            "end",
            "amount",
            "choice",
            "checked",
            "text",
            "notes",
            "created_by",
        )
