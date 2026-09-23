# -*- coding: utf-8 -*-
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from .models import DASHBOARD_CARDS, Settings, timezone_choices
from .widgets import DateInput
from core.models import Child


class BabyBuddyUserForm(forms.ModelForm):
    restrict_children = forms.BooleanField(
        required=False, label=_("Restrict to selected children")
    )
    allowed_children = forms.ModelMultipleChoiceField(
        queryset=Child.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Allowed children"),
    )
    is_read_only = forms.BooleanField(
        required=False,
        label=_("Read only"),
        help_text=_("Restricts user to viewing data only."),
    )
    is_caregiver = forms.BooleanField(
        required=False,
        label=_("Caregiver"),
        help_text=_(
            "Allows adding and editing care entries (feedings, diaper changes, "
            "sleep, timers, medication, temperature, weight, notes and tummy "
            "time) for allowed children. Cannot delete entries or reach pumping, "
            "height, BMI, head circumference, user management or settings."
        ),
    )
    access_expires = forms.SplitDateTimeField(
        required=False,
        label=_("Access expires"),
        input_date_formats=["%Y-%m-%d"],
        input_time_formats=["%H:%M", "%I:%M %p"],
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_read_only",
            "is_caregiver",
            "is_active",
            "access_expires",
            "restrict_children",
            "allowed_children",
        ]

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop("user", None)
        data = kwargs.get("data")
        if (
            data is not None
            and "access_expires" in data
            and "access_expires_0" not in data
        ):
            data = data.copy()
            try:
                value = forms.DateTimeField(required=False).clean(
                    data["access_expires"]
                )
                from django.utils import timezone

                value = timezone.localtime(value) if value else None
                data["access_expires_0"] = value.strftime("%Y-%m-%d") if value else ""
                data["access_expires_1"] = value.strftime("%H:%M") if value else ""
            except forms.ValidationError:
                data["access_expires_0"] = data["access_expires"]
                data["access_expires_1"] = ""
            kwargs["data"] = data
        user = kwargs["instance"]
        if user:
            kwargs["initial"].update(
                {
                    "is_read_only": user.groups.filter(
                        name=settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"]
                    ).exists(),
                    "is_caregiver": user.groups.filter(
                        name=settings.BABY_BUDDY["CAREGIVER_GROUP_NAME"]
                    ).exists(),
                    "access_expires": user.settings.access_expires,
                    "restrict_children": user.settings.restrict_children,
                    "allowed_children": user.settings.allowed_children.all(),
                }
            )
        super(BabyBuddyUserForm, self).__init__(*args, **kwargs)
        from core.entry_timing import time_widget

        widget = forms.SplitDateTimeWidget()
        widget.widgets = [
            DateInput(attrs={"aria-label": _("Expiration date")}),
            time_widget(actor),
        ]
        widget.widgets[1].attrs["aria-label"] = _("Expiration time")
        self.fields["access_expires"].widget = widget

    def clean_access_expires(self):
        value = self.cleaned_data.get("access_expires")
        old = self.instance.settings.access_expires if self.instance.pk else None
        if value and old and value == old.replace(second=0, microsecond=0):
            return old
        return value

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_read_only") and cleaned_data.get("is_caregiver"):
            self.add_error(
                "is_caregiver",
                _("A user cannot be both read only and caregiver."),
            )
        if cleaned_data.get("is_staff") and cleaned_data.get("is_caregiver"):
            self.add_error(
                "is_caregiver",
                _("A user cannot be both staff and caregiver."),
            )
        if cleaned_data.get("restrict_children") and (
            cleaned_data.get("is_staff")
            or not (
                cleaned_data.get("is_read_only") or cleaned_data.get("is_caregiver")
            )
        ):
            self.add_error(
                "restrict_children",
                _(
                    "Use a caregiver or read-only account without staff access for child restrictions."
                ),
            )
        return cleaned_data

    def save(self, commit=True):
        user = super(BabyBuddyUserForm, self).save(commit=False)
        is_read_only = self.cleaned_data["is_read_only"]
        is_caregiver = self.cleaned_data.get("is_caregiver", False)
        if is_read_only or is_caregiver:
            user.is_superuser = False
        else:
            user.is_superuser = True
        if commit:
            user.save()
            user.settings.access_expires = self.cleaned_data.get("access_expires")
            user.settings.restrict_children = self.cleaned_data.get(
                "restrict_children", False
            )
            user.settings.save(update_fields=["access_expires", "restrict_children"])
            user.settings.allowed_children.set(
                self.cleaned_data.get("allowed_children", [])
            )
        readonly_group = Group.objects.get(
            name=settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"]
        )
        caregiver_group = Group.objects.get(
            name=settings.BABY_BUDDY["CAREGIVER_GROUP_NAME"]
        )
        if is_read_only:
            user.groups.add(readonly_group.id)
        else:
            user.groups.remove(readonly_group.id)
        if is_caregiver:
            user.groups.add(caregiver_group.id)
        else:
            user.groups.remove(caregiver_group.id)
        return user


class UserAddForm(BabyBuddyUserForm, UserCreationForm):
    pass


class UserUpdateForm(BabyBuddyUserForm):
    pass


class UserForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]


class UserPasswordForm(PasswordChangeForm):
    class Meta:
        fields = ["old_password", "new_password1", "new_password2"]


class UserSettingsForm(forms.ModelForm):
    from core.feature_preferences import OPTIONAL_FIELDS, activity_choices

    shown_activities = forms.MultipleChoiceField(
        required=False,
        choices=activity_choices,
        widget=forms.CheckboxSelectMultiple,
        label=_("Activities to show"),
    )
    shown_entry_fields = forms.MultipleChoiceField(
        required=False,
        choices=[(key, value[0]) for key, value in OPTIONAL_FIELDS.items()],
        widget=forms.CheckboxSelectMultiple,
        label=_("Optional fields to show"),
    )
    hide_field_help = True
    unit_fields = ("liquid_unit", "length_unit", "weight_unit", "temperature_unit")
    timezone = forms.ChoiceField(label=_("Timezone"))
    dashboard_cards = forms.MultipleChoiceField(
        choices=DASHBOARD_CARDS,
        label=_("Dashboard cards"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timezone"].choices = timezone_choices()
        for shown, hidden in (
            ("shown_activities", "hidden_activities"),
            ("shown_entry_fields", "hidden_entry_fields"),
        ):
            self.initial[shown] = [
                key
                for key, _label in self.fields[shown].choices
                if key not in (getattr(self.instance, hidden) or [])
            ]
        self.fields["dashboard_refresh_rate"].label = _("Refresh dashboard")
        self.fields["pagination_count"].label = _("Entries per page")
        # Older clients may not send a theme; keep the default rather than fail.
        self.fields["theme"].required = False
        for field in self.unit_fields:
            self.fields[field].required = False
        hidden = self.instance.dashboard_hidden_cards or []
        self.initial["dashboard_cards"] = [
            key for key, _label in DASHBOARD_CARDS if key not in hidden
        ]

    def clean(self):
        cleaned = super().clean()
        for field in self.unit_fields:
            if field not in self.errors and not cleaned.get(field):
                cleaned[field] = getattr(self.instance, field)
        return cleaned

    def clean_theme(self):
        return self.cleaned_data.get("theme") or "dark"

    def save(self, commit=True):
        # The marker distinguishes "show nothing" from older clients that do
        # not submit these preferences at all. Keep the existing stored format.
        for shown, hidden in (
            ("shown_activities", "hidden_activities"),
            ("shown_entry_fields", "hidden_entry_fields"),
        ):
            if self.data.get("entry_preferences_present") == "1":
                selected = set(self.cleaned_data[shown])
                setattr(
                    self.instance,
                    hidden,
                    [
                        key
                        for key, _label in self.fields[shown].choices
                        if key not in selected
                    ],
                )
        # The checkbox list is absent from the POST both when every card is
        # unchecked and when a client never sent it; a marker tells them apart.
        if self.data.get("dashboard_cards_present"):
            shown = set(self.cleaned_data.get("dashboard_cards") or [])
            self.instance.dashboard_hidden_cards = [
                key for key, _label in DASHBOARD_CARDS if key not in shown
            ]
        return super().save(commit=commit)

    class Meta:
        model = Settings
        fields = [
            "dashboard_refresh_rate",
            "dashboard_hide_empty",
            "dashboard_hide_age",
            "language",
            "theme",
            "liquid_unit",
            "length_unit",
            "weight_unit",
            "temperature_unit",
            "timezone",
            "timezone_follow_device",
            "use_24_hour_time",
            "pagination_count",
        ]
