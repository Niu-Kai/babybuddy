# -*- coding: utf-8 -*-
from django import forms
from django.forms import widgets
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from taggit.forms import TagField, TagWidgetMixin

from babybuddy.widgets import DateInput, DateTimeInput, TimeInput
from core import fields, models
from core.models import Timer
from core.widgets import (
    TagsEditor,
    ChildRadioSelect,
    PillRadioSelect,
    SavedLocationInput,
    AppointmentTimeInput,
    AppointmentDurationInput,
)


def set_initial_values(kwargs, form_type):
    """
    Sets initial value for add forms based on provided kwargs.

    :param kwargs: Keyword arguments.
    :param form_type: Class of the type of form being initialized.
    :return: Keyword arguments with updated "initial" values.
    """

    # Never update initial values for existing instance (e.g. edit operation).
    if kwargs.get("instance", None):
        kwargs.pop("child", None)
        kwargs.pop("timer", None)
        return kwargs

    # Add the "initial" kwarg if it does not already exist.
    if not kwargs.get("initial"):
        kwargs.update(initial={})

    # Set Child based on `child` kwarg or single Chile database.
    child_slug = kwargs.get("child", None)
    if child_slug:
        kwargs["initial"].update(
            {
                "child": models.Child.objects.filter(slug=child_slug).first(),
            }
        )
    elif models.Child.count() == 1:
        kwargs["initial"].update({"child": models.Child.objects.first()})

    # Set start and end time based on Timer from `timer` kwarg.
    timer_id = kwargs.get("timer", None)
    if timer_id:
        try:
            timer = models.Timer.objects.get(id=timer_id)
            if timer.context.get("activity") == form_type._meta.model._meta.model_name:
                for key in ("type", "method"):
                    if key in timer.context:
                        kwargs["initial"].setdefault(key, timer.context[key])
            kwargs["initial"].update(
                # The end excludes time the timer spent paused (#190).
                {
                    "timer": timer,
                    "start": timer.start,
                    "end": timer.start + timer.duration(),
                }
            )
        except (Timer.DoesNotExist, ValueError, TypeError, OverflowError):
            pass

    # Set type and method values for Feeding instance based on last feed.
    if (
        form_type == FeedingForm
        and "child" in kwargs["initial"]
        and "method" not in kwargs["initial"]
    ):
        last_feeding = (
            models.Feeding.objects.filter(child=kwargs["initial"]["child"])
            .order_by("end")
            .last()
        )
        if last_feeding:
            last_method = last_feeding.method
            last_feed_args = {"type": last_feeding.type}
            if last_method not in ["left breast", "right breast"]:
                last_feed_args["method"] = last_method
            kwargs["initial"].update(last_feed_args)

    # Pre-fill the diaper change amount from the site setting (#990).
    if form_type == DiaperChangeForm and "amount" not in kwargs["initial"]:
        default_amount = models.DiaperChange.settings.default_amount
        if default_amount:
            kwargs["initial"].update({"amount": default_amount})

    # Set default "nap" value for Sleep instances.
    if form_type == SleepForm and "nap" not in kwargs["initial"]:
        try:
            start = timezone.localtime(kwargs["initial"]["start"]).time()
        except KeyError:
            start = timezone.localtime().time()
        nap = (
            models.Sleep.settings.nap_start_min
            <= start
            <= models.Sleep.settings.nap_start_max
        )
        kwargs["initial"].update({"nap": nap})

    # Remove custom kwargs, so they do not interfere with `super` calls.
    for key in ["child", "timer"]:
        try:
            kwargs.pop(key)
        except KeyError:
            pass

    return kwargs


class CoreModelForm(forms.ModelForm):
    hide_field_help = True

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", getattr(self, "user", None))
        # Set `timer_id` so the Timer can be consumed only after a successful save.
        self.timer_id = kwargs.get("timer", None)
        kwargs = set_initial_values(kwargs, type(self))
        super(CoreModelForm, self).__init__(*args, **kwargs)
        if "child" in self.fields:
            from core.access import scoped

            self.fields["child"].queryset = scoped(
                models.Child.objects.all(), self.user
            )
        self.use_tolerant_fields()
        self.add_overlap_field()
        self.hide_single_child()
        self.add_copy_time_hint()
        self.add_timer_field()
        from core.units import setup_unit_field

        setup_unit_field(self)
        from core.entry_timing import setup_entry_timing

        setup_entry_timing(self)

    def hide_single_child(self):
        """
        With exactly one child there is nothing to choose, so the child field
        becomes a hidden input (babybuddy/babybuddy#889). `set_initial_values`
        has already provided the initial value.
        """
        if "child" in self.fields and models.Child.count() == 1:
            self.fields["child"].widget = forms.HiddenInput()

    def add_copy_time_hint(self):
        """Label for the client-side "copy start time" button (#728)."""
        if "start" in self.fields and "end" in self.fields:
            self.fields["end"].widget.attrs["data-copy-label"] = _("Copy start time")

    def add_overlap_field(self):
        """
        Entries with a start and end are validated to not overlap another
        entry. When that validation fails the form re-renders with a
        confirmation checkbox so the entry can be saved anyway
        (babybuddy/babybuddy#702, #736).
        """
        self.overlap_conflict = False
        names = {field.name for field in self._meta.model._meta.get_fields()}
        if {"start", "end"} <= names:
            self.fields["allow_overlap"] = forms.BooleanField(
                required=False,
                label=_("Save anyway, even though it overlaps another entry"),
                widget=forms.HiddenInput(),
            )

    def _post_clean(self):
        if "allow_overlap" in self.fields:
            self.instance.allow_overlap = bool(self.cleaned_data.get("allow_overlap"))
        super()._post_clean()
        if "allow_overlap" in self.fields and any(
            error.code == "period_intersection"
            for error in self.non_field_errors().as_data()
        ):
            self.overlap_conflict = True
            self.fields["allow_overlap"].widget = forms.CheckboxInput()

    def use_tolerant_fields(self):
        """
        Swap the generated date/time and number fields for variants that
        accept daylight saving transition times and comma decimals.
        """
        for field in self.fields.values():
            if type(field) is forms.DateTimeField:
                field.__class__ = fields.DateTimeField
            elif type(field) is forms.FloatField:
                field.__class__ = fields.FloatField

    def add_timer_field(self):
        """
        Add a read-only field with the name of the Timer being stopped.

        The form is usually opened from a Timer, so showing which Timer the
        entry belongs to makes it possible to identify the timer after the
        fact. The Timer is only a source of initial values, so the field is
        disabled and not used when the form is saved.
        """
        if not self.timer_id:
            return

        try:
            timer = models.Timer.objects.filter(id=self.timer_id).first()
        except (ValueError, TypeError, OverflowError):
            return

        if not timer:
            return

        self.fields["timer"] = forms.CharField(
            label=_("Timer"),
            required=False,
            disabled=True,
        )
        self.initial["timer"] = timer.title_with_child
        self.fields = self.move_after(self.fields, "timer", "child")

        if hasattr(self, "fieldsets"):
            self.fieldsets = [
                {
                    **fieldset,
                    "fields": self.move_after(fieldset["fields"], "timer", "child"),
                }
                for fieldset in self.fieldsets
            ]

    @staticmethod
    def move_after(fields, item, anchor):
        """Return the fields with `item` placed directly after `anchor`."""
        if item == anchor or anchor not in fields:
            return fields

        if isinstance(fields, dict):
            if item not in fields:
                return fields

            items = list(fields.items())
            entry = items.pop([key for key, _ in items].index(item))
            items.insert([key for key, _ in items].index(anchor) + 1, entry)
            return dict(items)

        fields = list(fields)
        if item in fields:
            fields.remove(item)
        fields.insert(fields.index(anchor) + 1, item)
        return fields

    def clean(self):
        cleaned_data = super().clean()
        from core.units import clean_unit_fields

        clean_unit_fields(self, cleaned_data)
        from core.entry_timing import clean_entry_timing

        clean_entry_timing(self, cleaned_data)
        if self.timer_id is not None:
            try:
                timer = models.Timer.objects.get(pk=self.timer_id)
            except (Timer.DoesNotExist, ValueError, TypeError, OverflowError):
                raise forms.ValidationError(_("This timer does not exist."))
            if self.user is None or not timer.can_be_consumed_by(self.user):
                raise PermissionDenied(
                    _("You do not have permission to consume timers.")
                )
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            timer = None
            if self.timer_id is not None:
                # Lock until the entry and its tags have been saved successfully.
                timer = (
                    models.Timer.objects.select_for_update()
                    .filter(pk=self.timer_id)
                    .first()
                )
                if timer is None:
                    raise forms.ValidationError(_("This timer no longer exists."))
                # The timer may have changed owner since validation.
                if self.user is None or not timer.can_be_consumed_by(self.user):
                    raise PermissionDenied(
                        _("You do not have permission to consume timers.")
                    )
            if instance.pk is None and self.user is not None:
                if hasattr(instance, "created_by"):
                    instance.created_by = self.user
            instance.save()
            self.save_m2m()
            if timer is not None:
                timer.stop()
        return instance

    @property
    def hydrated_fielsets(self):
        # for some reason self.fields returns defintions and not bound fields
        # so until i figure out a better way we can just create a dict here
        # https://github.com/django/django/blob/main/django/forms/forms.py#L52

        bound_field_dict = {}
        for field in self:
            bound_field_dict[field.name] = field

        hydrated_fieldsets = []

        for fieldset in self.fieldsets:
            hyrdrated_fieldset = {
                "layout": fieldset.get("layout", "default"),
                "layout_attrs": fieldset.get("layout_attrs", {}),
                "fields": [],
            }
            for field_name in fieldset["fields"]:
                hyrdrated_fieldset["fields"].append(bound_field_dict[field_name])

            hydrated_fieldsets.append(hyrdrated_fieldset)

        return hydrated_fieldsets


class HiddenTagWidget(TagWidgetMixin, forms.HiddenInput):
    """Hidden tag input that still renders tag names instead of object reprs."""


class TaggableModelForm(forms.ModelForm):
    tags = TagField(
        label=_("Tags"),
        widget=TagsEditor,
        required=False,
        strip=True,
        help_text=_(
            "Click on the tags to add (+) or remove (-) tags or use the text editor to create new tags."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is None or not self.user.has_perm("core.change_tag"):
            # Without `change_tag` the field stays in the form (the layout and
            # the preserved value depend on it) but is only a carrier for the
            # current tag names, which `clean_tags` accepts unchanged.
            self.fields["tags"].widget = HiddenTagWidget()
            self.fields["tags"].help_text = None

    def clean_tags(self):
        current = list(self.instance.tags.names()) if self.instance.pk else []
        if self.add_prefix("tags") not in self.data:
            return current
        tags = self.cleaned_data["tags"]
        models.Tag.check_assignment_permissions(self.user, tags, current)
        return tags


class BMIForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "bmi", "date"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.BMI
        fields = ["child", "bmi", "date", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class BottleFeedingForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "type", "start", "amount"], "layout": "required"},
        {"fields": ["secondary_type", "secondary_amount"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solid food does not come in a bottle (babybuddy/babybuddy#767).
        self.fields["type"].choices = [
            choice
            for choice in self.fields["type"].choices
            if choice[0] != "solid food"
        ]

    def clean(self):
        cleaned_data = super().clean()
        if "start" in cleaned_data:
            self.instance.end = cleaned_data["start"]
        return cleaned_data

    def save(self, commit=True):
        self.instance.method = "bottle"
        self.instance.end = self.instance.start
        return super().save(commit=commit)

    class Meta:
        model = models.Feeding
        fields = [
            "child",
            "start",
            "type",
            "amount",
            "secondary_type",
            "secondary_amount",
            "notes",
            "tags",
        ]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "type": PillRadioSelect(),
            "secondary_type": PillRadioSelect(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class ChildForm(forms.ModelForm):
    hide_field_help = True

    slug = forms.SlugField(
        allow_unicode=True,
        label=_("Slug"),
        max_length=100,
        required=False,
        help_text=_(
            "Used in this child's web addresses. Leave empty to derive it from "
            "the name."
        ),
    )

    class Meta:
        model = models.Child
        fields = ["first_name", "last_name", "birth_date", "birth_time", "due_date"]
        if settings.BABY_BUDDY["ALLOW_UPLOADS"]:
            fields.append("picture")
        widgets = {
            "birth_date": DateInput(),
            "birth_time": TimeInput(),
            "due_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        from core.entry_timing import time_widget, TIME_FORMATS

        self.fields["birth_time"].widget = time_widget(user, seconds=True)
        self.fields["birth_time"].input_formats = TIME_FORMATS + [
            "%H:%M:%S",
            "%I:%M:%S %p",
        ]
        if self.instance.pk:
            self.initial["slug"] = self.instance.slug
        else:
            del self.fields["slug"]
            now = timezone.localtime().replace(second=0, microsecond=0)
            self.initial.setdefault("birth_date", now.date())
            self.initial.setdefault("birth_time", now.time())

    def clean_picture(self):
        picture = self.cleaned_data.get("picture")
        if picture and hasattr(picture, "content_type"):
            from core.photos import prepare_photo

            return prepare_photo(picture)
        return picture

    def clean_birth_time(self):
        value = self.cleaned_data.get("birth_time")
        old = self.instance.birth_time
        # Explicit seconds, including :00, are editable; minute-only legacy
        # submissions preserve existing precision.
        raw = self.data.get(self.add_prefix("birth_time"), "")
        if raw.count(":") >= 2:
            return value
        if (
            self.instance.pk
            and value
            and old
            and value == old.replace(second=0, microsecond=0)
        ):
            return old
        return value

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "")
        if not slug:
            return ""
        slug = slugify(slug, allow_unicode=True)
        conflict = models.Child.objects.filter(slug=slug).exclude(pk=self.instance.pk)
        if conflict.exists():
            raise forms.ValidationError(
                _("Another child already uses this slug."), code="slug_taken"
            )
        return slug

    def save(self, commit=True):
        if "slug" in self.fields:
            self.instance.slug = self.cleaned_data.get("slug") or ""
        if not self.instance.slug:
            self.instance.slug = slugify(self.instance, allow_unicode=True)
        return super().save(commit=commit)


class ChildDeleteForm(forms.ModelForm):
    confirm_name = forms.CharField(max_length=511)

    class Meta:
        model = models.Child
        fields = []

    def clean_confirm_name(self):
        confirm_name = self.cleaned_data["confirm_name"]
        if confirm_name != str(self.instance):
            raise forms.ValidationError(
                _("Name does not match child name."), code="confirm_mismatch"
            )
        return confirm_name

    def save(self, commit=True):
        instance = self.instance
        self.instance.delete()
        return instance


class DiaperChangeForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "time"], "layout": "required"},
        {
            "fields": ["wet", "solid"],
            "layout": "choices",
            "layout_attrs": {"label": "Contents"},
        },
        {"fields": ["color", "amount"]},
        {"layout": "advanced", "fields": ["notes", "tags"]},
    ]

    class Meta:
        model = models.DiaperChange
        fields = ["child", "time", "wet", "solid", "color", "amount", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect(),
            "color": PillRadioSelect(),
            "time": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class FeedingForm(CoreModelForm, TaggableModelForm):
    from core.meal_foods import MealFoodsWidget

    foods = forms.Field(label=_("Foods"), required=False, widget=MealFoodsWidget)

    fieldsets = [
        {"fields": ["child", "start", "end", "type", "method"], "layout": "required"},
        {"fields": ["foods"]},
        {"fields": ["amount", "last_breast"]},
        {"fields": ["secondary_type", "secondary_amount"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.top_ups import setup_top_up_form

        setup_top_up_form(self)
        from core.meal_foods import food_suggestions

        self.fields["foods"].widget.suggestions = food_suggestions(self.user)
        if self.instance.pk:
            self.initial["foods"] = list(
                self.instance.foods.values("id", "name", "reaction")
            )
        if self.user and not self.user.has_perm("core.view_food"):
            self.fields["foods"].disabled = True
            self.fields["foods"].widget = forms.HiddenInput()
            self.initial["foods"] = []

        # The duration is optional (babybuddy/babybuddy#772): an entry without
        # an end time is stored as an instant, like a bottle feeding.
        self.fields["end"].required = False
        self.fields["end"].help_text = _(
            "Leave blank to record the feeding without a duration."
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("start") and not cleaned_data.get("end"):
            cleaned_data["end"] = cleaned_data["start"]
        # "Ended on" only means something for both breasts (#1012).
        if cleaned_data.get("method") != "both breasts":
            cleaned_data["last_breast"] = None
        from core.meal_foods import normalize_foods, validate_meal_foods

        if "foods" not in self.errors:
            try:
                rows = normalize_foods(cleaned_data.get("foods") or [])
                # Omitted controls from older clients preserve existing exposures.
                if self.is_bound and self.add_prefix("foods_name") not in self.data:
                    rows = normalize_foods(
                        list(self.instance.foods.values("id", "name", "reaction"))
                        if self.instance.pk
                        else []
                    )
                self.instance.type = cleaned_data.get("type", self.instance.type)
                self.instance.secondary_type = cleaned_data.get("secondary_type")
                validate_meal_foods(self.instance, rows, self.user)
                cleaned_data["foods"] = rows
            except forms.ValidationError as error:
                self.add_error("foods", error)
        from core.top_ups import clean_top_up_form

        clean_top_up_form(self, cleaned_data)
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            from core.meal_foods import save_meal_foods

            save_meal_foods(instance, self.cleaned_data.get("foods", []), self.user)
        return instance

    class Meta:
        model = models.Feeding
        fields = [
            "child",
            "start",
            "end",
            "type",
            "method",
            "amount",
            "secondary_type",
            "secondary_amount",
            "top_up_at",
            "top_up_type",
            "top_up_amount",
            "top_up_secondary_type",
            "top_up_secondary_amount",
            "last_breast",
            "notes",
            "tags",
        ]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "type": PillRadioSelect(),
            "method": PillRadioSelect(),
            "secondary_type": PillRadioSelect(),
            "last_breast": PillRadioSelect(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class HeadCircumferenceForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "head_circumference", "date"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.HeadCircumference
        fields = ["child", "head_circumference", "date", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class HeightForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "height", "date"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Height
        fields = ["child", "height", "date", "notes", "tags"]
        help_texts = {
            "height": _("The WHO percentile report expects centimeters."),
        }
        widgets = {
            "child": ChildRadioSelect,
            "date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class MedicationForm(CoreModelForm, TaggableModelForm):
    next_dose_interval = forms.DecimalField(
        label=_("Time Until Next Dosage"),
        required=False,
        min_value=0,
        initial=0,
        help_text=_("Optional: Hours until next dose can be given"),
    )

    fieldsets = [
        {
            "fields": [
                "child",
                "time",
                "next_dose_interval",
                "name",
                "dosage",
                "dosage_unit",
            ],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Medication
        fields = [
            "child",
            "name",
            "dosage",
            "dosage_unit",
            "time",
            "next_dose_interval",
            "notes",
            "tags",
        ]
        widgets = {
            "child": ChildRadioSelect,
            "dosage_unit": PillRadioSelect(),
            "time": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.urls import reverse

        if (
            self.user
            and self.user.has_perm("core.view_medication")
            and not self.instance.pk
        ):
            self.fields["name"].widget.attrs.update(
                {
                    "data-medication-choices": reverse("core:medication-choices"),
                    "autocomplete": "off",
                    "list": "medication-history",
                }
            )
        # Convert existing timedelta to hours for display
        if self.instance and self.instance.next_dose_interval:
            total_seconds = self.instance.next_dose_interval.total_seconds()
            self.initial["next_dose_interval"] = total_seconds / 3600

    def clean_next_dose_interval(self):
        hours = self.cleaned_data.get("next_dose_interval")
        if hours is not None and hours > 0:
            return timezone.timedelta(hours=float(hours))
        return None


class PumpingForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["start", "end"], "layout": "required"},
        {"fields": ["left_amount", "right_amount", "amount", "side"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].required = False
        self.fields["amount"].label = _("Total amount")
        self.fields["amount"].widget.attrs["data-pumping-total"] = ""

    def clean(self):
        data = super().clean()
        from core.pumping import set_pumping_total

        entry = models.Pumping(
            amount=data.get("amount"),
            left_amount=data.get("left_amount"),
            right_amount=data.get("right_amount"),
        )
        try:
            set_pumping_total(entry)
            data["amount"] = entry.amount
            if entry.left_amount is not None or entry.right_amount is not None:
                data["side"] = entry.side
        except forms.ValidationError as error:
            for field, errors in error.message_dict.items():
                self.add_error(field, errors)
        return data

    class Meta:
        model = models.Pumping
        fields = [
            "start",
            "end",
            "left_amount",
            "right_amount",
            "amount",
            "side",
            "notes",
            "tags",
        ]
        widgets = {
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "side": PillRadioSelect(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class AppointmentTimingForm(forms.Form):
    reference_start = forms.DateTimeField(required=False, widget=forms.HiddenInput())
    appointment_date = forms.DateField(label=_("Date"), widget=DateInput())
    start_time = forms.TimeField(
        label=_("Start time"),
        input_formats=["%H:%M", "%I:%M %p"],
        widget=forms.TimeInput(format="%I:%M %p", attrs={"placeholder": "1:30 PM"}),
        help_text=_("Choose a time or type one, such as 1:30 PM or 13:30."),
    )
    duration_minutes = fields.FloatField(
        label=_("Duration (minutes)"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": "any"}),
        help_text=_(
            "Choose a duration or type the number of minutes. Leave blank if unknown."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.local_times import configure

        configure(self)

    def clean(self):
        import datetime

        data = super().clean()
        if self.errors:
            return data
        try:
            from core.local_times import resolve

            start = resolve(self, data, data.get("reference_start"))
            if start is None:
                return data
            duration = data.get("duration_minutes")
            end = (
                None
                if duration is None
                else timezone.localtime(
                    start.astimezone(datetime.timezone.utc)
                    + datetime.timedelta(minutes=duration)
                )
            )
            data.update(start=start, end=end)
        except (OverflowError, ValueError, forms.ValidationError):
            self.add_error(
                "duration_minutes", _("Choose a valid date, time, and duration.")
            )
        return data


class AppointmentForm(CoreModelForm, TaggableModelForm):
    appointment_date = AppointmentTimingForm.base_fields["appointment_date"]
    start_time = AppointmentTimingForm.base_fields["start_time"]
    duration_minutes = AppointmentTimingForm.base_fields["duration_minutes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        import datetime

        schedule_fields = ("appointment_date", "start_time", "duration_minutes")
        self.legacy_times = (
            self.is_bound
            and self.add_prefix("start") in self.data
            and not any(self.add_prefix(name) in self.data for name in schedule_fields)
        )
        self.fields["start"].required = self.legacy_times
        if self.legacy_times:
            for name in schedule_fields:
                self.fields[name].required = False
        initial_start = self.initial.get("start") or (
            self.instance.start
            if self.instance.pk
            else timezone.now().replace(second=0, microsecond=0)
        )
        initial_start = timezone.localtime(initial_start)
        self.entry_original_start = initial_start if self.instance.pk else None
        from core.local_times import configure

        configure(self, self.entry_original_start)
        initial_end = self.initial.get("end")
        self.initial.setdefault("appointment_date", initial_start.date().isoformat())
        clock_format = (
            "%H:%M" if self.user and self.user.settings.use_24_hour_time else "%I:%M %p"
        )
        time_choices = [
            datetime.time(hour, minute).strftime(clock_format)
            for hour in range(24)
            for minute in (0, 15, 30, 45)
        ]
        self.fields["start_time"].widget = AppointmentTimeInput(
            format=clock_format,
            attrs={
                "placeholder": "13:30" if clock_format == "%H:%M" else "1:30 PM",
                "autocomplete": "off",
            },
            choices=[(value, value) for value in time_choices],
            choice_label=_("Choose a start time"),
            choice_kind="time",
        )
        self.fields["duration_minutes"].widget = AppointmentDurationInput(
            attrs={"inputmode": "decimal", "autocomplete": "off", "placeholder": "30"},
            choices=[
                ("15", _("15 minutes")),
                ("30", _("30 minutes")),
                ("45", _("45 minutes")),
                ("60", _("1 hour (60 minutes)")),
                ("90", _("1.5 hours (90 minutes)")),
                ("120", _("2 hours (120 minutes)")),
                ("", _("No end time")),
            ],
            choice_label=_("Choose a duration"),
            choice_kind="duration",
        )
        self.initial.setdefault(
            "start_time",
            (
                initial_start.strftime(clock_format)
                if self.instance.pk or self.initial.get("start")
                else ""
            ),
        )
        if initial_end is not None:
            minutes = (
                initial_end.astimezone(datetime.timezone.utc)
                - initial_start.astimezone(datetime.timezone.utc)
            ).total_seconds() / 60
        else:
            minutes = None if self.instance.pk else 30
        self.initial.setdefault("duration_minutes", minutes)
        locations = []
        if self.user and self.user.has_perm("core.view_appointment"):
            recent = (
                models.Appointment.objects.exclude(location="")
                .order_by("-start", "-pk")
                .values_list("location", flat=True)[:200]
            )
            seen = set()
            for location in recent:
                location = location.strip()
                if location and location.casefold() not in seen:
                    seen.add(location.casefold())
                    locations.append(location)
                if len(locations) == 50:
                    break
        field = self.fields["location"]
        field.widget = SavedLocationInput(attrs=field.widget.attrs, locations=locations)
        field.help_text = _(
            "Type a location or choose one used in a previous appointment."
        )

    def clean(self):
        data = super().clean()
        if not self.legacy_times:
            names = (
                "appointment_date",
                "start_time",
                "duration_minutes",
                "time_occurrence",
                "entry_reference",
            )
            if not any(name in self.errors for name in names):
                schedule = AppointmentTimingForm(
                    {name: data.get(name) for name in names}
                )
                if schedule.is_valid():
                    data["start"] = schedule.cleaned_data["start"]
                    data["end"] = schedule.cleaned_data["end"]
                    # Keep an existing timestamp's precision (and DST fold) when
                    # only unrelated fields or the duration were edited.
                    if self.instance.pk and not data.get("time_occurrence"):
                        original = timezone.localtime(self.instance.start)
                        if (
                            original.date() == data["appointment_date"]
                            and original.time().replace(second=0, microsecond=0)
                            == data["start_time"]
                        ):
                            import datetime

                            duration = data["duration_minutes"]
                            data["start"] = original
                            data["end"] = (
                                None
                                if duration is None
                                else timezone.localtime(
                                    original.astimezone(datetime.timezone.utc)
                                    + datetime.timedelta(minutes=duration)
                                )
                            )
                else:
                    self.fields["time_occurrence"] = schedule.fields["time_occurrence"]
                    for name, errors in schedule.errors.items():
                        self.add_error(name, errors)
        return data

    fieldsets = [
        {"fields": ["child", "title"], "layout": "required"},
        {
            "fields": ["appointment_date", "start_time", "duration_minutes"],
            "layout": "appointment_time",
        },
        {"fields": ["location"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Appointment
        fields = ["child", "title", "start", "end", "location", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": forms.HiddenInput(),
            "end": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class NoteForm(CoreModelForm, TaggableModelForm):
    class Meta:
        model = models.Note
        fields = ["child", "note", "time", "tags"]
        if settings.BABY_BUDDY["ALLOW_UPLOADS"]:
            fields.insert(2, "image")
        widgets = {
            "child": ChildRadioSelect,
            "time": DateTimeInput(),
        }


class SleepForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "start", "end", "nap"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Sleep
        fields = ["child", "start", "end", "nap", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class TagAdminForm(CoreModelForm):
    fieldsets = [
        {
            "fields": ["name", "color"],
            "layout": "required",
        },
        {"fields": ["dashboard"]},
    ]

    class Meta:
        model = models.Tag
        fields = ["name", "color", "dashboard"]
        readonly_fields = ["slug"]
        widgets = {
            "color": widgets.TextInput(
                attrs={"type": "color", "class": "form-control-color"}
            )
        }


class TemperatureForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "temperature", "time"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Temperature
        fields = ["child", "temperature", "time", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "time": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class TimerForm(CoreModelForm):
    activity = forms.ChoiceField(
        required=False,
        label=_("Activity"),
        choices=[
            ("", _("Choose when stopping")),
            ("feeding", _("Feeding")),
            ("sleep", _("Sleep")),
            ("pumping", _("Pumping")),
            ("tummytime", _("Tummy time")),
            ("bathtime", _("Bath")),
        ],
    )

    def clean(self):
        data = super().clean()
        previous = self.instance.context or {}
        activity = data.get("activity")
        self.instance.context = (
            previous
            if activity == previous.get("activity")
            else ({"activity": activity} if activity else {})
        )
        return data

    class Meta:
        model = models.Timer
        fields = ["child", "name", "start"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(TimerForm, self).__init__(*args, **kwargs)
        self.initial["activity"] = self.instance.context.get("activity", "")

    def save(self, commit=True):
        instance = super(TimerForm, self).save(commit=False)
        if instance.user_id is None:
            instance.user = self.user
            instance.save()
        else:
            # Editing a timer does not change its owner, including an owner
            # changed by someone else while the form was open.
            instance.save(update_fields=[*self._meta.fields, "context"])
        return instance


class TummyTimeForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "start", "end"], "layout": "required"},
        {"fields": ["milestone"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.TummyTime
        fields = ["child", "start", "end", "milestone", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class WeightForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {
            "fields": ["child", "weight", "date", "time"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Weight
        fields = ["child", "weight", "date", "time", "notes", "tags"]
        help_texts = {
            "weight": _("The WHO percentile report expects kilograms."),
        }
        widgets = {
            "child": ChildRadioSelect,
            "date": DateInput(),
            "time": TimeInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class BathTimeForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "start", "end"], "layout": "required"},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.BathTime
        fields = ["child", "start", "end", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "notes": forms.Textarea(attrs={"rows": 5}),
            "start": DateTimeInput(),
            "end": DateTimeInput(),
        }


class RefluxForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "time", "severity"], "layout": "required"},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Reflux
        fields = ["child", "time", "severity", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "notes": forms.Textarea(attrs={"rows": 5}),
            "time": DateTimeInput(),
            "severity": PillRadioSelect(),
        }


class FoodForm(CoreModelForm, TaggableModelForm):
    fieldsets = [
        {"fields": ["child", "time", "name"], "layout": "required"},
        {"fields": ["amount", "reaction"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.feeding_id:
            for name in ("child", "time", "appointment_date", "start_time"):
                if name in self.fields:
                    self.fields[name].disabled = True

    class Meta:
        model = models.Food
        fields = ["child", "time", "name", "amount", "reaction", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "notes": forms.Textarea(attrs={"rows": 5}),
            "time": DateTimeInput(),
            "reaction": PillRadioSelect(),
        }


class TimelineFilterForm(forms.Form):
    period = forms.ChoiceField(
        required=False,
        label=_("Period"),
        choices=[
            ("all", _("All dates")),
            ("day", _("Day")),
            ("week", _("Week")),
            ("month", _("Month")),
            ("year", _("Year")),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date = forms.DateField(
        required=False,
        label=_("Date in period"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    activity = forms.ChoiceField(
        required=False,
        label=_("Activity"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, user, **kwargs):
        if args:
            data = args[0].copy()
            # Existing day-filter links continue to select that day.
            if not data.get("period"):
                data["period"] = "day" if data.get("date") else "all"
            if data["period"] != "all" and not data.get("date"):
                data["date"] = timezone.localdate().isoformat()
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        activities = (
            ("feeding", _("Feeding")),
            ("sleep", _("Sleep")),
            ("diaperchange", _("Diaper changes")),
            ("pumping", _("Pumping")),
            ("medication", _("Medication")),
            ("tummytime", _("Tummy time")),
            ("bathtime", _("Bath time")),
            ("reflux", _("Reflux")),
            ("food", _("Food")),
            ("note", _("Notes")),
            ("temperature", _("Temperature")),
            ("customactivity", _("Custom activities")),
        )
        self.fields["activity"].choices = [("", _("All activities"))] + [
            (name, label)
            for name, label in activities
            if user.has_perm("core.view_" + name)
        ]

    def clean(self):
        import calendar
        import datetime

        cleaned = super().clean()
        period = cleaned.get("period", "all")
        anchor = cleaned.get("date")
        cleaned["range_start"] = cleaned["range_end"] = None
        if period == "all" or not anchor:
            return cleaned
        try:
            start = end = anchor
            if period == "week":
                # Weeks run Sunday through Saturday, shown explicitly in the UI.
                start = anchor - datetime.timedelta(days=(anchor.weekday() + 1) % 7)
                end = start + datetime.timedelta(days=6)
            elif period == "month":
                start = anchor.replace(day=1)
                end = anchor.replace(
                    day=calendar.monthrange(anchor.year, anchor.month)[1]
                )
            elif period == "year":
                start = anchor.replace(month=1, day=1)
                end = anchor.replace(month=12, day=31)
            cleaned["range_start"], cleaned["range_end"] = start, end
        except (OverflowError, ValueError):
            self.add_error(
                "date", _("Choose a date within a complete calendar period.")
            )
        return cleaned


class CalendarFilterForm(TimelineFilterForm):
    def __init__(self, data=None, *, user, **kwargs):
        data = (data or {}).copy()
        if not data.get("period"):
            data["period"] = "month"
        if not data.get("date") and data.get("month"):
            data["date"] = data["month"] + "-01"
        super().__init__(data, user=user, **kwargs)
        self.fields.pop("activity")
        self.fields["period"].choices = [
            (value, label)
            for value, label in self.fields["period"].choices
            if value != "all"
        ]


class RecordPeriodFilterForm(TimelineFilterForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("activity")


class PumpingReminderForm(forms.Form):
    hide_field_help = True
    enabled = forms.BooleanField(label=_("Show a reminder in the app"), required=False)
    minutes = forms.IntegerField(
        label=_("Remind me after (minutes)"),
        required=False,
        min_value=1,
        max_value=10080,
    )
    basis = forms.ChoiceField(
        label=_("Count from the end of"),
        choices=[
            ("combined", _("Last pumping or nursing session")),
            ("pumping", _("Last pumping session")),
        ],
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.initial.update(
            enabled=bool(user.settings.pumping_reminder_minutes),
            minutes=user.settings.pumping_reminder_minutes,
            basis=user.settings.pumping_reminder_basis,
        )
        if not user.has_perm("core.view_feeding"):
            self.fields["basis"].choices = [("pumping", _("Last pumping session"))]
            self.initial["basis"] = "pumping"

    def clean(self):
        data = super().clean()
        if data.get("enabled") and not data.get("minutes"):
            self.add_error("minutes", _("Enter a reminder interval."))
        return data

    def save(self):
        self.user.settings.pumping_reminder_minutes = (
            self.cleaned_data["minutes"] if self.cleaned_data["enabled"] else None
        )
        self.user.settings.pumping_reminder_basis = self.cleaned_data["basis"]
        self.user.settings.save(
            update_fields=["pumping_reminder_minutes", "pumping_reminder_basis"]
        )
