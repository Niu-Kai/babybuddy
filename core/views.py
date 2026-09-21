# -*- coding: utf-8 -*-
import datetime

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.db.models.functions import Lower
from django.forms import Form, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import View
from django.views.generic.base import RedirectView, TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView, FormView

from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin
from babybuddy.views import BabyBuddyFilterView, BabyBuddyPaginatedView
from core import filters, forms, models, timeline


def _prepare_timeline_context_data(context, date, child=None, user=None):
    date = timezone.datetime.strptime(date, "%Y-%m-%d")
    date = timezone.localtime(timezone.make_aware(date))
    context["timeline_objects"] = timeline.get_objects(date, child, user)
    context["date"] = date
    context["date_previous"] = date - timezone.timedelta(days=1)
    if date.date() < timezone.localdate():
        context["date_next"] = date + timezone.timedelta(days=1)
    pass


class CoreFormMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = str(
            getattr(self, "success_url", "") or reverse("dashboard:dashboard")
        )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if issubclass(self.get_form_class(), (forms.CoreModelForm, forms.ChildForm)):
            kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)


class CoreAddView(
    CoreFormMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView
):
    def get_success_message(self, cleaned_data):
        cleaned_data["model"] = self.model._meta.verbose_name.title()
        if "child" in cleaned_data:
            self.success_message = _("%(model)s entry for %(child)s added!")
        else:
            self.success_message = _("%(model)s entry added!")
        return self.success_message % cleaned_data

    def get_form_kwargs(self):
        """
        Check for and add "child" and "timer" from request query parameters.
          - "child" may provide a slug for a Child instance.
          - "timer" may provided an ID for a Timer instance.

        These arguments are used in some add views to pre-fill initial data in
        the form fields.

        :return: Updated keyword arguments.
        """
        kwargs = super(CoreAddView, self).get_form_kwargs()
        if issubclass(self.get_form_class(), forms.CoreModelForm):
            from core.presentation import presentation

            selected = presentation(self.request)["selected_child"]
            if selected:
                kwargs["child"] = selected.slug
            for parameter in ["child", "timer"]:
                if parameter in self.request.GET:
                    kwargs[parameter] = self.request.GET[parameter]
        return kwargs


class CoreUpdateView(
    CoreFormMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView
):
    def get_success_message(self, cleaned_data):
        cleaned_data["model"] = self.model._meta.verbose_name.title()
        if cleaned_data.get("child"):
            self.success_message = _("%(model)s entry for %(child)s updated.")
        else:
            self.success_message = _("%(model)s entry updated.")
        return self.success_message % cleaned_data


class CoreDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    def get_success_message(self, cleaned_data):
        return _("%(model)s entry deleted.") % {
            "model": self.model._meta.verbose_name.title()
        }


class BMIList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.BMI
    template_name = "core/bmi_list.html"
    permission_required = ("core.view_bmi",)
    filterset_class = filters.BMIFilter

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(source_weight__isnull=False, source_height__isnull=False)
        )


class BMIAdd(PermissionRequiredMixin, RedirectView):
    permission_required = ("core.view_bmi",)
    pattern_name = "core:bmi-list"
    http_method_names = ["get", "head", "options"]

    def get_redirect_url(self, *args, **kwargs):
        return reverse("core:bmi-list")


class BMIUpdate(BMIAdd):
    pass


class BMIDelete(BMIAdd):
    pass


class ChildList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Child
    template_name = "core/child_list.html"
    permission_required = ("core.view_child",)
    filterset_fields = ("first_name", "last_name")


class ChildAdd(CoreAddView):
    model = models.Child
    permission_required = ("core.add_child",)
    form_class = forms.ChildForm
    success_url = reverse_lazy("core:child-list")
    success_message = _("%(first_name)s %(last_name)s added!")


class ChildDetail(PermissionRequiredMixin, DetailView):
    model = models.Child
    permission_required = ("core.view_child",)

    template_name = "timeline/timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        view = Timeline()
        view.setup(self.request)
        return view.get_context_data(**context)


class ChildUpdate(CoreUpdateView):
    model = models.Child
    permission_required = ("core.change_child",)
    form_class = forms.ChildForm
    success_url = reverse_lazy("core:child-list")


class ChildDelete(CoreUpdateView):
    model = models.Child
    form_class = forms.ChildDeleteForm
    template_name = "core/child_confirm_delete.html"
    permission_required = ("core.delete_child",)
    success_url = reverse_lazy("core:child-list")

    def get_success_message(self, cleaned_data):
        """This class cannot use `CoreDeleteView` because of the confirmation
        step required so the success message must be overridden."""
        success_message = _("%(model)s entry deleted.") % {
            "model": self.model._meta.verbose_name.title()
        }
        return success_message % cleaned_data


class DiaperChangeList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.DiaperChange
    template_name = "core/diaperchange_list.html"
    permission_required = ("core.view_diaperchange",)
    filterset_class = filters.DiaperChangeFilter


class DiaperChangeAdd(CoreAddView):
    model = models.DiaperChange
    permission_required = ("core.add_diaperchange",)
    form_class = forms.DiaperChangeForm
    success_url = reverse_lazy("core:diaperchange-list")


class DiaperChangeUpdate(CoreUpdateView):
    model = models.DiaperChange
    permission_required = ("core.change_diaperchange",)
    form_class = forms.DiaperChangeForm
    success_url = reverse_lazy("core:diaperchange-list")


class DiaperChangeDelete(CoreDeleteView):
    model = models.DiaperChange
    permission_required = ("core.delete_diaperchange",)
    success_url = reverse_lazy("core:diaperchange-list")


class FeedingList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Feeding
    template_name = "core/feeding_list.html"
    permission_required = ("core.view_feeding",)
    filterset_class = filters.FeedingFilter


class FeedingAdd(CoreAddView):
    model = models.Feeding
    permission_required = ("core.add_feeding",)
    form_class = forms.FeedingForm
    success_url = reverse_lazy("core:feeding-list")


class BottleFeedingAdd(CoreAddView):
    model = models.Feeding
    permission_required = ("core.add_feeding",)
    form_class = forms.BottleFeedingForm
    success_url = reverse_lazy("core:feeding-list")


class FeedingUpdate(CoreUpdateView):
    model = models.Feeding
    permission_required = ("core.change_feeding",)
    form_class = forms.FeedingForm
    success_url = reverse_lazy("core:feeding-list")


class FeedingDelete(CoreDeleteView):
    model = models.Feeding
    permission_required = ("core.delete_feeding",)
    success_url = reverse_lazy("core:feeding-list")


class HeadCircumferenceList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.HeadCircumference
    template_name = "core/head_circumference_list.html"
    permission_required = ("core.view_headcircumference",)
    filterset_class = filters.HeadCircumferenceFilter


class HeadCircumferenceAdd(CoreAddView):
    model = models.HeadCircumference
    template_name = "core/head_circumference_form.html"
    permission_required = ("core.add_headcircumference",)
    form_class = forms.HeadCircumferenceForm
    success_url = reverse_lazy("core:head-circumference-list")


class HeadCircumferenceUpdate(CoreUpdateView):
    model = models.HeadCircumference
    template_name = "core/head_circumference_form.html"
    permission_required = ("core.change_headcircumference",)
    form_class = forms.HeadCircumferenceForm
    success_url = reverse_lazy("core:head-circumference-list")


class HeadCircumferenceDelete(CoreDeleteView):
    model = models.HeadCircumference
    template_name = "core/head_circumference_confirm_delete.html"
    permission_required = ("core.delete_headcircumference",)
    success_url = reverse_lazy("core:head-circumference-list")


class HeightList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Height
    template_name = "core/height_list.html"
    permission_required = ("core.view_height",)
    filterset_class = filters.HeightFilter


class HeightAdd(CoreAddView):
    model = models.Height
    permission_required = ("core.add_height",)
    form_class = forms.HeightForm
    success_url = reverse_lazy("core:height-list")


class HeightUpdate(CoreUpdateView):
    model = models.Height
    permission_required = ("core.change_height",)
    form_class = forms.HeightForm
    success_url = reverse_lazy("core:height-list")


class HeightDelete(CoreDeleteView):
    model = models.Height
    permission_required = ("core.delete_height",)
    success_url = reverse_lazy("core:height-list")


class MedicationList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.Medication
    template_name = "core/medication_list.html"
    permission_required = ("core.view_medication",)
    filterset_class = filters.MedicationFilter


class MedicationAdd(CoreAddView):
    model = models.Medication
    permission_required = ("core.add_medication",)
    form_class = forms.MedicationForm
    success_url = reverse_lazy("core:medication-list")

    def get_initial(self):
        """
        `?repeat=<id>` pre-fills the form from an existing entry so a repeat
        dose is one click away (babybuddy/babybuddy#1068).
        """
        initial = super().get_initial()
        try:
            source = models.Medication.objects.get(id=self.request.GET.get("repeat"))
        except (models.Medication.DoesNotExist, ValueError, TypeError):
            return initial
        initial.update(
            {
                "child": source.child,
                "name": source.name,
                "dosage": source.dosage,
                "dosage_unit": source.dosage_unit,
            }
        )
        if source.next_dose_interval:
            initial["next_dose_interval"] = (
                source.next_dose_interval.total_seconds() / 3600
            )
        return initial


class MedicationUpdate(CoreUpdateView):
    model = models.Medication
    permission_required = ("core.change_medication",)
    form_class = forms.MedicationForm
    success_url = reverse_lazy("core:medication-list")


class MedicationDelete(CoreDeleteView):
    model = models.Medication
    permission_required = ("core.delete_medication",)
    success_url = reverse_lazy("core:medication-list")


class AppointmentList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.Appointment
    template_name = "core/appointment_list.html"
    permission_required = ("core.view_appointment",)
    filterset_class = filters.AppointmentFilter

    def get_queryset(self):
        queryset = super().get_queryset()
        # Upcoming by default; `?past=1` shows everything, newest first.
        if self.request.GET.get("past"):
            return queryset.order_by("-start")
        return queryset.filter(
            start__gte=timezone.now() - timezone.timedelta(days=1)
        ).order_by("start")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_past"] = bool(self.request.GET.get("past"))
        context["children"] = models.Child.objects.all()
        return context


class AppointmentCalendar(PermissionRequiredMixin, TemplateView):
    """Appointments in local day, week, month, and year views."""

    template_name = "core/appointment_calendar.html"
    permission_required = ("core.view_appointment",)

    def get_context_data(self, **kwargs):
        import calendar
        from collections import defaultdict
        from django.db.models import Q
        from django.utils.formats import date_format
        from urllib.parse import urlencode
        from core.presentation import presentation

        context = super().get_context_data(**kwargs)
        scope = presentation(self.request)
        form = forms.CalendarFilterForm(self.request.GET, user=self.request.user)
        context.update(
            calendar_filter=form,
            today=timezone.localdate(),
            unique_child=bool(scope["selected_child"]),
        )
        if not form.is_valid():
            return context
        first, last = form.cleaned_data["range_start"], form.cleaned_data["range_end"]
        period = form.cleaned_data["period"]
        context.update(period=period, range_start=first, range_end=last)

        def link(mode, anchor):
            return "?" + urlencode(
                {
                    "period": mode,
                    "date": anchor.isoformat(),
                    "scope": scope["child_scope"],
                }
            )

        for key, boundary, offset in (
            ("previous_period_url", first, -1),
            ("next_period_url", last, 1),
        ):
            try:
                context[key] = link(period, boundary + datetime.timedelta(days=offset))
            except OverflowError:
                pass

        start = timezone.make_aware(datetime.datetime.combine(first, datetime.time.min))
        end = timezone.make_aware(datetime.datetime.combine(last, datetime.time.max))
        # Clamp only dates whose UTC conversion exceeds Python's date limits.
        try:
            start = start.astimezone(datetime.timezone.utc)
        except OverflowError:
            start = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        try:
            end = end.astimezone(datetime.timezone.utc)
        except OverflowError:
            end = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
        appointments = (
            models.Appointment.objects.filter(start__lte=end)
            .filter(Q(start__gte=start) | Q(end__gt=start))
            .select_related("child")
            .order_by("start", "pk")
        )
        if scope["selected_child"]:
            appointments = appointments.filter(child=scope["selected_child"])
        appointments = list(appointments)
        context["appointment_count"] = len(appointments)
        by_day = defaultdict(list)
        for appointment in appointments:
            starts = timezone.localtime(appointment.start)
            ends = timezone.localtime(appointment.end) if appointment.end else starts
            # An appointment ending at midnight belongs to the preceding day.
            final_day = (
                (ends - datetime.timedelta(microseconds=1)).date()
                if ends > starts
                else starts.date()
            )
            day = max(first, starts.date())
            final_day = min(last, final_day)
            while day <= final_day:
                by_day[day].append(
                    {
                        "appointment": appointment,
                        "continues": starts.date() < day,
                        "multi_day": starts.date() != ends.date(),
                    }
                )
                if day == final_day:
                    break
                day += datetime.timedelta(days=1)

        def day_context(day, in_month=True):
            return {
                "date": day,
                "in_month": in_month,
                "entries": by_day.get(day, []),
                "url": link("day", day),
            }

        def month_context(month_start):
            weeks = []
            # Out-of-month cells are blank, including at Python's year limits.
            for week in calendar.Calendar(calendar.SUNDAY).monthdayscalendar(
                month_start.year, month_start.month
            ):
                weeks.append(
                    [
                        day_context(month_start.replace(day=day)) if day else None
                        for day in week
                    ]
                )
            ids = {
                entry["appointment"].pk
                for day, entries in by_day.items()
                if day.month == month_start.month and day.year == month_start.year
                for entry in entries
            }
            return {
                "date": month_start,
                "weeks": weeks,
                "url": link("month", month_start),
                "count": len(ids),
            }

        context["weekday_names"] = [
            date_format(datetime.date(2026, 1, 4) + datetime.timedelta(days=i), "D")
            for i in range(7)
        ]
        if period == "year":
            context["calendar_months"] = [
                month_context(first.replace(month=month)) for month in range(1, 13)
            ]
        elif period == "month":
            context["calendar_month"] = month_context(first)
        else:
            context["calendar_days"] = [
                day_context(first + datetime.timedelta(days=i))
                for i in range((last - first).days + 1)
            ]
        return context


class AppointmentEndPreview(PermissionRequiredMixin, View):
    def has_permission(self):
        return self.request.user.has_perm(
            "core.add_appointment"
        ) or self.request.user.has_perm("core.change_appointment")

    def get(self, request):
        from django.http import JsonResponse
        from django.utils.formats import date_format, time_format
        from babybuddy import preferences

        form = forms.AppointmentTimingForm(request.GET)
        if not form.is_valid():
            return JsonResponse(
                {"display": _("Enter a valid date, time, and duration.")}, status=400
            )
        end = form.cleaned_data["end"]
        if end is None:
            return JsonResponse({"end": None, "display": _("No end time set")})
        return JsonResponse(
            {
                "end": end.isoformat(),
                "display": date_format(end, "DATE_FORMAT")
                + " · "
                + time_format(end, preferences.get_time_format() or "TIME_FORMAT"),
            }
        )


class EntryEndPreview(AppointmentEndPreview):
    def has_permission(self):
        name = self.kwargs["model_name"]
        return name in {"feeding", "pumping", "sleep", "tummytime", "bathtime"} and (
            self.request.user.has_perm(f"core.add_{name}")
            or self.request.user.has_perm(f"core.change_{name}")
        )

    def get(self, request, model_name):
        if model_name != "feeding" and not request.GET.get("duration_minutes"):
            from django.http import JsonResponse

            return JsonResponse({"display": "—"})
        # An unknown feeding duration is stored as an instant.
        if model_name == "feeding" and not request.GET.get("duration_minutes"):
            data = request.GET.copy()
            data["duration_minutes"] = "0"
            request.GET = data
        return super().get(request)


class AppointmentAdd(CoreAddView):
    model = models.Appointment
    permission_required = ("core.add_appointment",)
    form_class = forms.AppointmentForm
    success_url = reverse_lazy("core:appointment-list")


class AppointmentUpdate(CoreUpdateView):
    model = models.Appointment
    permission_required = ("core.change_appointment",)
    form_class = forms.AppointmentForm
    success_url = reverse_lazy("core:appointment-list")


class AppointmentDelete(CoreDeleteView):
    model = models.Appointment
    permission_required = ("core.delete_appointment",)
    success_url = reverse_lazy("core:appointment-list")


class AppointmentFeed(View):
    """
    iCalendar feed of a child's appointments for calendar apps such as
    Google Calendar ("From URL"). Authenticated by the user's API key in
    `?token=`, since calendar apps cannot log in.
    """

    def get(self, request, slug):
        from django.http import HttpResponse, HttpResponseForbidden
        from rest_framework.authtoken.models import Token

        token = Token.objects.filter(key=request.GET.get("token", "")).first()
        user = token.user if token else None
        if (
            user is None
            or not user.is_active
            or user.settings.access_expired
            or not user.has_perm("core.view_appointment")
        ):
            return HttpResponseForbidden("Invalid token.")
        child = get_object_or_404(models.Child, slug=slug)
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Baby Buddy//Appointments//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{child} - Baby Buddy",
        ]
        for appointment in models.Appointment.objects.filter(child=child):
            lines.extend(appointment.ical_event())
        lines.append("END:VCALENDAR")
        response = HttpResponse(
            "\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8"
        )
        response["Content-Disposition"] = f'inline; filename="{child.slug}.ics"'
        return response


class NoteList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Note
    template_name = "core/note_list.html"
    permission_required = ("core.view_note",)
    filterset_class = filters.NoteFilter


class NoteAdd(CoreAddView):
    model = models.Note
    permission_required = ("core.add_note",)
    form_class = forms.NoteForm
    success_url = reverse_lazy("core:note-list")


class NoteUpdate(CoreUpdateView):
    model = models.Note
    permission_required = ("core.change_note",)
    form_class = forms.NoteForm
    success_url = reverse_lazy("core:note-list")


class NoteDelete(CoreDeleteView):
    model = models.Note
    permission_required = ("core.delete_note",)
    success_url = reverse_lazy("core:note-list")


class PumpingList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Pumping
    template_name = "core/pumping_list.html"
    permission_required = ("core.view_pumping",)
    filterset_class = filters.PumpingFilter


class PumpingAdd(CoreAddView):
    model = models.Pumping
    permission_required = ("core.add_pumping",)
    form_class = forms.PumpingForm
    success_url = reverse_lazy("core:pumping-list")
    success_message = _("%(model)s entry added!")


class PumpingUpdate(CoreUpdateView):
    model = models.Pumping
    permission_required = ("core.change_pumping",)
    form_class = forms.PumpingForm
    success_url = reverse_lazy("core:pumping-list")
    success_message = _("%(model)s entry for %(child)s updated.")


class PumpingDelete(CoreDeleteView):
    model = models.Pumping
    permission_required = ("core.delete_pumping",)
    success_url = reverse_lazy("core:pumping-list")


class SleepList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Sleep
    template_name = "core/sleep_list.html"
    permission_required = ("core.view_sleep",)
    filterset_class = filters.SleepFilter


class SleepAdd(CoreAddView):
    model = models.Sleep
    permission_required = ("core.add_sleep",)
    form_class = forms.SleepForm
    success_url = reverse_lazy("core:sleep-list")


class SleepUpdate(CoreUpdateView):
    model = models.Sleep
    permission_required = ("core.change_sleep",)
    form_class = forms.SleepForm
    success_url = reverse_lazy("core:sleep-list")


class SleepDelete(CoreDeleteView):
    model = models.Sleep
    permission_required = ("core.delete_sleep",)
    success_url = reverse_lazy("core:sleep-list")


class TagAdminList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.Tag
    template_name = "core/tag_list.html"
    permission_required = ("core.view_tag",)
    filterset_class = filters.TagFilter

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(Count("core_tagged_items"))
            .order_by(Lower("name"))
        )


class TagAdminDetail(PermissionRequiredMixin, DetailView):
    model = models.Tag
    permission_required = ("core.view_tag",)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = []
        for title, definitions in (
            (
                _("Measurements"),
                (
                    (models.Weight, "weight", _("Weight")),
                    (models.Height, "height", _("Height")),
                    (
                        models.HeadCircumference,
                        "head-circumference",
                        _("Head circumference"),
                    ),
                    (models.Temperature, "temperature", _("Temperature")),
                ),
            ),
            (
                _("Activities"),
                (
                    (models.Feeding, "feeding", _("Feedings")),
                    (models.DiaperChange, "diaperchange", _("Diaper changes")),
                    (models.Sleep, "sleep", _("Sleep")),
                    (models.Pumping, "pumping", _("Pumping")),
                    (models.TummyTime, "tummytime", _("Tummy time")),
                    (models.BathTime, "bathtime", _("Bath time")),
                    (models.Reflux, "reflux", _("Reflux")),
                    (models.Food, "food", _("Foods")),
                    (models.Medication, "medication", _("Medication")),
                    (models.Note, "note", _("Notes")),
                    (models.Appointment, "appointment", _("Appointments")),
                ),
            ),
        ):
            entries = []
            for model, route, label in definitions:
                if self.request.user.has_perm(
                    f"{model._meta.app_label}.view_{model._meta.model_name}"
                ):
                    entries.append(
                        {
                            "label": label,
                            "count": model.objects.filter(tags=self.object).count(),
                            "url": reverse("core:" + route + "-list")
                            + "?scope=all&tag="
                            + str(self.object.pk),
                        }
                    )
            if entries:
                sections.append({"title": title, "entries": entries})
        context["tag_sections"] = sections
        return context


class TagAdminAdd(CoreAddView):
    model = models.Tag
    permission_required = ("core.add_tag",)
    form_class = forms.TagAdminForm
    success_url = reverse_lazy("core:tag-list")


class TagAdminUpdate(CoreUpdateView):
    model = models.Tag
    permission_required = ("core.change_tag",)
    form_class = forms.TagAdminForm
    success_url = reverse_lazy("core:tag-list")


class TagAdminDelete(CoreDeleteView):
    model = models.Tag
    permission_required = ("core.delete_tag",)
    success_url = reverse_lazy("core:tag-list")

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(Count("core_tagged_items"))


class TemperatureList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.Temperature
    template_name = "core/temperature_list.html"
    permission_required = ("core.view_temperature",)
    filterset_class = filters.TemperatureFilter


class TemperatureAdd(CoreAddView):
    model = models.Temperature
    permission_required = ("core.add_temperature",)
    form_class = forms.TemperatureForm
    success_url = reverse_lazy("core:temperature-list")
    success_message = _("%(model)s reading added!")


class TemperatureUpdate(CoreUpdateView):
    model = models.Temperature
    permission_required = ("core.change_temperature",)
    form_class = forms.TemperatureForm
    success_url = reverse_lazy("core:temperature-list")
    success_message = _("%(model)s reading for %(child)s updated.")


class TemperatureDelete(CoreDeleteView):
    model = models.Temperature
    permission_required = ("core.delete_temperature",)
    success_url = reverse_lazy("core:temperature-list")


class Timeline(LoginRequiredMixin, TemplateView):
    template_name = "timeline/timeline.html"

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        from core.presentation import presentation

        context = super().get_context_data(**kwargs)
        scope = presentation(self.request)
        form = forms.TimelineFilterForm(self.request.GET, user=self.request.user)
        context["timeline_filter"] = form
        valid = form.is_valid()
        start = form.cleaned_data.get("range_start") if valid else None
        end = form.cleaned_data.get("range_end") if valid else None
        activity = form.cleaned_data.get("activity", "") if valid else ""
        period = form.cleaned_data.get("period", "all") if valid else "all"
        day = (
            timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
            if start
            else None
        )
        end_day = (
            timezone.make_aware(datetime.datetime.combine(end, datetime.time.min))
            if end
            else None
        )
        context.update(
            date=day,
            range_start=start,
            range_end=end,
            period=period,
            today=timezone.localdate(),
        )
        if start and end:
            for direction in (-1, 1):
                try:
                    anchor = (
                        (start - datetime.timedelta(days=1))
                        if direction < 0
                        else (end + datetime.timedelta(days=1))
                    )
                except OverflowError:
                    continue
                params = self.request.GET.copy()
                for key in list(params):
                    if key == "page" or key.startswith("page_child_"):
                        params.pop(key)
                params["date"] = anchor.isoformat()
                params["period"] = period
                context[
                    "previous_period_url" if direction < 0 else "next_period_url"
                ] = ("?" + params.urlencode())

        def entries(child, page_key):
            events = (
                timeline.get_objects(
                    day, child, self.request.user, activity, end_date=end_day
                )
                if valid
                else []
            )
            page = Paginator(events, 50).get_page(self.request.GET.get(page_key))
            return {
                "timeline_objects": page.object_list,
                "timeline_page": page,
                "timeline_page_key": page_key,
            }

        if scope["side_by_side"]:
            context["timeline_panels"] = [
                {"child": child, **entries(child, "page_child_" + str(child.pk))}
                for child in scope["scope_children"]
            ]
        else:
            context.update(entries(scope["selected_child"], "page"))
        return context


class TimerList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Timer
    template_name = "core/timer_list.html"
    permission_required = ("core.view_timer",)
    filterset_fields = ("user",)


class TimerDetail(PermissionRequiredMixin, DetailView):
    model = models.Timer
    permission_required = ("core.view_timer",)


class TimerAdd(PermissionRequiredMixin, CreateView):
    model = models.Timer
    permission_required = ("core.add_timer",)
    form_class = forms.TimerForm

    def get_form_kwargs(self):
        kwargs = super(TimerAdd, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        from core.presentation import presentation

        selected = presentation(self.request)["selected_child"]
        if selected:
            kwargs["child"] = selected.slug
        return kwargs

    def get_success_url(self):
        return reverse("core:timer-detail", kwargs={"pk": self.object.pk})


class TimerUpdate(CoreUpdateView):
    model = models.Timer
    permission_required = ("core.change_timer",)
    form_class = forms.TimerForm
    success_url = reverse_lazy("core:timer-list")

    def get_form_kwargs(self):
        kwargs = super(TimerUpdate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        from core.presentation import presentation

        selected = presentation(self.request)["selected_child"]
        if selected:
            kwargs["child"] = selected.slug
        return kwargs

    def get_success_url(self):
        instance = self.get_object()
        return reverse("core:timer-detail", kwargs={"pk": instance.pk})


class TimerAddQuick(PermissionRequiredMixin, RedirectView):
    http_method_names = ["post"]
    permission_required = ("core.add_timer",)

    def post(self, request, *args, **kwargs):
        instance = models.Timer.objects.create(user=request.user)
        # Find child from child pk in POST
        child_id = request.POST.get("child", False)
        child = models.Child.objects.get(pk=child_id) if child_id else None
        if child:
            instance.child = child
        # Add child relationship if there is only Child instance.
        elif models.Child.count() == 1:
            instance.child = models.Child.objects.first()
        instance.save()
        self.url = request.GET.get(
            "next", reverse("core:timer-detail", args={instance.id})
        )
        return super(TimerAddQuick, self).get(request, *args, **kwargs)


class TimerRestart(PermissionRequiredMixin, RedirectView):
    http_method_names = ["post"]
    permission_required = ("core.change_timer",)

    def post(self, request, *args, **kwargs):
        instance = models.Timer.objects.get(id=kwargs["pk"])
        instance.restart()
        messages.success(request, "{} restarted.".format(instance))
        return super(TimerRestart, self).get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("core:timer-detail", kwargs={"pk": kwargs["pk"]})


class TimerPause(PermissionRequiredMixin, RedirectView):
    http_method_names = ["post"]
    permission_required = ("core.change_timer",)

    def post(self, request, *args, **kwargs):
        instance = get_object_or_404(models.Timer, id=kwargs["pk"])
        instance.pause()
        messages.success(request, _("%(timer)s paused.") % {"timer": instance})
        return super().get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("core:timer-detail", kwargs={"pk": kwargs["pk"]})


class TimerResume(PermissionRequiredMixin, RedirectView):
    http_method_names = ["post"]
    permission_required = ("core.change_timer",)

    def post(self, request, *args, **kwargs):
        instance = get_object_or_404(models.Timer, id=kwargs["pk"])
        instance.resume()
        messages.success(request, _("%(timer)s resumed.") % {"timer": instance})
        return super().get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("core:timer-detail", kwargs={"pk": kwargs["pk"]})


class TimerDelete(CoreDeleteView):
    model = models.Timer
    permission_required = ("core.delete_timer",)
    success_url = reverse_lazy("core:timer-list")


class TummyTimeList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.TummyTime
    template_name = "core/tummytime_list.html"
    permission_required = ("core.view_tummytime",)
    filterset_class = filters.TummyTimeFilter


class TummyTimeAdd(CoreAddView):
    model = models.TummyTime
    permission_required = ("core.add_tummytime",)
    form_class = forms.TummyTimeForm
    success_url = reverse_lazy("core:tummytime-list")


class TummyTimeUpdate(CoreUpdateView):
    model = models.TummyTime
    permission_required = ("core.change_tummytime",)
    form_class = forms.TummyTimeForm
    success_url = reverse_lazy("core:tummytime-list")


class TummyTimeDelete(CoreDeleteView):
    model = models.TummyTime
    permission_required = ("core.delete_tummytime",)
    success_url = reverse_lazy("core:tummytime-list")


class WeightList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Weight
    template_name = "core/weight_list.html"
    permission_required = ("core.view_weight",)
    filterset_class = filters.WeightFilter


class WeightAdd(CoreAddView):
    model = models.Weight
    permission_required = ("core.add_weight",)
    form_class = forms.WeightForm
    success_url = reverse_lazy("core:weight-list")


class WeightUpdate(CoreUpdateView):
    model = models.Weight
    permission_required = ("core.change_weight",)
    form_class = forms.WeightForm
    success_url = reverse_lazy("core:weight-list")


class WeightDelete(CoreDeleteView):
    model = models.Weight
    permission_required = ("core.delete_weight",)
    success_url = reverse_lazy("core:weight-list")


class BathTimeList(
    PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView
):
    model = models.BathTime
    template_name = "core/bathtime_list.html"
    permission_required = ("core.view_bathtime",)
    filterset_class = filters.BathTimeFilter


class BathTimeAdd(CoreAddView):
    model = models.BathTime
    permission_required = ("core.add_bathtime",)
    form_class = forms.BathTimeForm
    success_url = reverse_lazy("core:bathtime-list")


class BathTimeUpdate(CoreUpdateView):
    model = models.BathTime
    permission_required = ("core.change_bathtime",)
    form_class = forms.BathTimeForm
    success_url = reverse_lazy("core:bathtime-list")


class BathTimeDelete(CoreDeleteView):
    model = models.BathTime
    permission_required = ("core.delete_bathtime",)
    success_url = reverse_lazy("core:bathtime-list")


class RefluxList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Reflux
    template_name = "core/reflux_list.html"
    permission_required = ("core.view_reflux",)
    filterset_class = filters.RefluxFilter


class RefluxAdd(CoreAddView):
    model = models.Reflux
    permission_required = ("core.add_reflux",)
    form_class = forms.RefluxForm
    success_url = reverse_lazy("core:reflux-list")


class RefluxUpdate(CoreUpdateView):
    model = models.Reflux
    permission_required = ("core.change_reflux",)
    form_class = forms.RefluxForm
    success_url = reverse_lazy("core:reflux-list")


class RefluxDelete(CoreDeleteView):
    model = models.Reflux
    permission_required = ("core.delete_reflux",)
    success_url = reverse_lazy("core:reflux-list")


class FoodList(PermissionRequiredMixin, BabyBuddyPaginatedView, BabyBuddyFilterView):
    model = models.Food
    template_name = "core/food_list.html"
    permission_required = ("core.view_food",)
    filterset_class = filters.FoodFilter


class FoodAdd(CoreAddView):
    model = models.Food
    permission_required = ("core.add_food",)
    form_class = forms.FoodForm
    success_url = reverse_lazy("core:food-list")


class FoodUpdate(CoreUpdateView):
    model = models.Food
    permission_required = ("core.change_food",)
    form_class = forms.FoodForm
    success_url = reverse_lazy("core:food-list")


class FoodDelete(CoreDeleteView):
    model = models.Food
    permission_required = ("core.delete_food",)
    success_url = reverse_lazy("core:food-list")
