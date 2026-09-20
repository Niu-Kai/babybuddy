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
from core.widgets import TagsEditor, ChildRadioSelect, PillRadioSelect


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
            kwargs["initial"].update(
                {"timer": timer, "start": timer.start, "end": timezone.now()}
            )
        except (Timer.DoesNotExist, ValueError, TypeError, OverflowError):
            pass

    # Set type and method values for Feeding instance based on last feed.
    if form_type == FeedingForm and "child" in kwargs["initial"]:
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
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", getattr(self, "user", None))
        # Set `timer_id` so the Timer can be consumed only after a successful save.
        self.timer_id = kwargs.get("timer", None)
        kwargs = set_initial_values(kwargs, type(self))
        super(CoreModelForm, self).__init__(*args, **kwargs)
        self.use_tolerant_fields()
        self.add_overlap_field()
        self.hide_single_child()
        self.add_copy_time_hint()
        self.add_timer_field()

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
        fields = ["child", "start", "type", "amount", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "type": PillRadioSelect(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class ChildForm(forms.ModelForm):
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
        fields = ["first_name", "last_name", "birth_date", "birth_time"]
        if settings.BABY_BUDDY["ALLOW_UPLOADS"]:
            fields.append("picture")
        widgets = {
            "birth_date": DateInput(),
            "birth_time": TimeInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["slug"] = self.instance.slug
        else:
            # New children always get a derived slug (babybuddy/babybuddy#923).
            del self.fields["slug"]

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
    fieldsets = [
        {"fields": ["child", "start", "end", "type", "method"], "layout": "required"},
        {"fields": ["amount"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        return cleaned_data

    class Meta:
        model = models.Feeding
        fields = ["child", "start", "end", "type", "method", "amount", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "type": PillRadioSelect(),
            "method": PillRadioSelect(),
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
            "height": _("The WHO percentile report expects centimetres."),
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
        {"fields": ["child", "start", "end"], "layout": "required"},
        {"fields": ["amount", "side"]},
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Pumping
        fields = ["child", "start", "end", "amount", "side", "notes", "tags"]
        widgets = {
            "child": ChildRadioSelect,
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "side": PillRadioSelect(),
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
        }
    ]

    class Meta:
        model = models.Tag
        fields = ["name", "color"]
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

    def save(self, commit=True):
        instance = super(TimerForm, self).save(commit=False)
        if instance.user_id is None:
            instance.user = self.user
            instance.save()
        else:
            # Editing a timer does not change its owner, including an owner
            # changed by someone else while the form was open.
            instance.save(update_fields=self._meta.fields)
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
            "fields": ["child", "weight", "date"],
            "layout": "required",
        },
        {"fields": ["notes", "tags"], "layout": "advanced"},
    ]

    class Meta:
        model = models.Weight
        fields = ["child", "weight", "date", "notes", "tags"]
        help_texts = {
            "weight": _("The WHO percentile report expects kilograms."),
        }
        widgets = {
            "child": ChildRadioSelect,
            "date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }
