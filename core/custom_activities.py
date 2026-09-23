"""Household-defined activities with optional, named fields."""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from babybuddy.mixins import PermissionRequiredMixin
from core import models
from core.forms import CoreModelForm, RecordPeriodFilterForm
from core.views import CoreAddView, CoreUpdateView, CoreDeleteView
from babybuddy.widgets import DateTimeInput


class ActivityTypeForm(forms.ModelForm):
    hide_field_help = True

    class Meta:
        model = models.ActivityType
        fields = [
            "name",
            "track_duration",
            "amount_label",
            "amount_unit",
            "choice_label",
            "choice_options",
            "check_label",
            "text_label",
            "archived",
        ]
        labels = {"name": _("Name"), "archived": _("Archived")}
        widgets = {
            "choice_options": forms.Textarea(
                attrs={"rows": 3, "placeholder": _("One option per line")}
            )
        }


class CustomActivityForm(CoreModelForm):
    class Meta:
        model = models.CustomActivity
        fields = [
            "child",
            "activity_type",
            "start",
            "end",
            "amount",
            "choice",
            "checked",
            "text",
            "notes",
        ]
        labels = {
            "child": _("Child"),
            "activity_type": _("Activity type"),
            "notes": _("Notes"),
        }
        widgets = {
            "start": DateTimeInput(),
            "end": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        types = models.ActivityType.objects.filter(archived=False)
        selected = (
            self.instance.activity_type_id
            if self.instance.pk
            else (
                self.data.get("activity_type")
                if self.is_bound
                else self.initial.get("activity_type")
            )
        )
        try:
            definition = (
                models.ActivityType.objects.filter(pk=selected).first()
                if selected
                else types.first()
            )
        except (ValueError, TypeError):
            definition = None
        self.fields["activity_type"].queryset = (
            models.ActivityType.objects.all() if self.instance.pk else types
        )
        self.fields["activity_type"].disabled = True
        if definition:
            self.initial["activity_type"] = definition.pk
            for field, label in (
                ("amount", definition.amount_label),
                ("choice", definition.choice_label),
                ("checked", definition.check_label),
                ("text", definition.text_label),
            ):
                if not label:
                    self.fields[field].widget = forms.HiddenInput()
                    self.fields[field].disabled = True
                else:
                    self.fields[field].label = label + (
                        " (" + definition.amount_unit + ")"
                        if field == "amount" and definition.amount_unit
                        else ""
                    )
            if definition.choice_label:
                choices = [("", "—")] + [(v, v) for v in definition.options()]
                if (
                    self.instance.choice
                    and self.instance.choice not in definition.options()
                ):
                    choices.append((self.instance.choice, self.instance.choice))
                self.fields["choice"] = forms.ChoiceField(
                    required=False, choices=choices, label=definition.choice_label
                )
            if not definition.track_duration and "duration_minutes" in self.fields:
                self.fields["duration_minutes"].widget = forms.HiddenInput()
                self.fields["duration_minutes"].disabled = True

    def clean(self):
        data = super().clean()
        if data.get("start") and not data.get("end"):
            data["end"] = data["start"]
        return data


class ActivityTypeList(PermissionRequiredMixin, ListView):
    model = models.ActivityType
    permission_required = "core.view_activitytype"
    template_name = "core/custom_types.html"


class TypeFormMixin:
    model = models.ActivityType
    form_class = ActivityTypeForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("core:custom-types")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "title": _("Edit activity type") if self.object else _("Add activity type"),
            "cancel_url": self.success_url,
        }


class ActivityTypeAdd(TypeFormMixin, PermissionRequiredMixin, CreateView):
    permission_required = "core.add_activitytype"


class ActivityTypeEdit(TypeFormMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "core.change_activitytype"


class CustomActivityList(PermissionRequiredMixin, ListView):
    model = models.CustomActivity
    permission_required = "core.view_customactivity"
    template_name = "core/custom_list.html"
    paginate_by = 50

    def get_queryset(self):
        from core.presentation import presentation

        qs = super().get_queryset().select_related("child", "activity_type")
        self.period = RecordPeriodFilterForm(self.request.GET, user=self.request.user)
        if not self.period.is_valid():
            return qs.none()
        child = presentation(self.request)["selected_child"]
        if child:
            qs = qs.filter(child=child)
        first, last = self.period.cleaned_data.get(
            "range_start"
        ), self.period.cleaned_data.get("range_end")
        if first:
            qs = qs.filter(start__date__range=(first, last))
        return qs

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "period_form": self.period}


class CustomFormMixin:
    model = models.CustomActivity
    form_class = CustomActivityForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("core:customactivity-list")

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("activity_type"):
            initial["activity_type"] = self.request.GET["activity_type"]
        return initial

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "title": _("Edit activity") if self.object else _("Add activity"),
        }


class CustomActivityAdd(CustomFormMixin, CoreAddView):
    permission_required = "core.add_customactivity"

    def get(self, request, *args, **kwargs):
        from django.shortcuts import redirect, get_object_or_404

        if not request.GET.get("activity_type"):
            return redirect("core:custom-types")
        try:
            pk = int(request.GET["activity_type"])
        except ValueError:
            from django.http import Http404

            raise Http404
        get_object_or_404(models.ActivityType, pk=pk, archived=False)
        return super().get(request, *args, **kwargs)


class CustomActivityEdit(CustomFormMixin, CoreUpdateView):
    permission_required = "core.change_customactivity"


class CustomActivityDelete(CoreDeleteView):
    model = models.CustomActivity
    permission_required = "core.delete_customactivity"
    template_name = "core/custom_confirm_delete.html"
    success_url = reverse_lazy("core:customactivity-list")


from django.views import View


class PottyPreset(PermissionRequiredMixin, View):
    permission_required = "core.add_activitytype"

    def post(self, request):
        from django.shortcuts import redirect

        definition, created = models.ActivityType.objects.get_or_create(
            name="Potty attempt",
            defaults={
                "choice_label": "Pee / poop",
                "choice_options": "Pee\nPoop\nBoth\nNeither",
                "check_label": "Successful attempt",
            },
        )
        return redirect("core:custom-types")
