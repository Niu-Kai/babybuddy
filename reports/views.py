# -*- coding: utf-8 -*-
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic.detail import DetailView

from babybuddy.mixins import PermissionRequiredMixin
from core import models

from . import graphs


def report_period(request):
    from core.forms import RecordPeriodFilterForm

    if not hasattr(request, "_report_period"):
        request._report_period = RecordPeriodFilterForm(request.GET, user=request.user)
        request._report_period.is_valid()
    return request._report_period


def report_entries(model, request, **filters):
    from datetime import date
    from django.db.models import DateTimeField, DateField

    queryset = model.objects.filter(**filters)
    fields = {field.name: field for field in model._meta.fields}
    name = next(
        (
            key
            for key in ("start", "time", "date")
            if key in fields and isinstance(fields[key], (DateField, DateTimeField))
        ),
        None,
    )
    period = report_period(request)
    if not period.is_valid():
        return queryset.none()
    if name:
        lookup = name + ("__date" if isinstance(fields[name], DateTimeField) else "")
        first, last = period.cleaned_data.get("range_start"), period.cleaned_data.get(
            "range_end"
        )
        if first:
            queryset = queryset.filter(
                **{lookup + "__gte": first, lookup + "__lte": last}
            )
        elif "period" not in request.GET:
            # Existing bookmarked ranges remain valid until a period is chosen.
            for parameter, operation in (("from", "gte"), ("to", "lte")):
                try:
                    value = date.fromisoformat(request.GET.get(parameter, ""))
                except ValueError:
                    continue
                queryset = queryset.filter(**{lookup + "__" + operation: value})
    return queryset


class ReportPresentationMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = report_period(self.request)
        context.update(
            report_period=period,
            report_range_start=period.cleaned_data.get("range_start"),
            report_range_end=period.cleaned_data.get("range_end"),
            today=timezone.localdate(),
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        from core.presentation import presentation

        scope = presentation(self.request)
        if (
            not scope["selected_child"]
            and self.template_name != "reports/report_list.html"
        ):
            panels = []
            for child in scope["scope_children"]:
                if context.get("object") and child.pk == context["object"].pk:
                    panels.append(context.copy())
                    continue
                view = type(self)()
                view.setup(self.request, **{**self.kwargs, "slug": child.slug})
                view.object = child
                panel = view.get_context_data(object=child)
                panels.append(panel)
            context["report_panels"] = panels
        return super().render_to_response(context, **response_kwargs)


class ReportsHome(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    model = models.Child
    permission_required = ("core.view_child",)
    template_name = "reports/report_list.html"

    def get_object(self, queryset=None):
        from core.presentation import presentation

        scope = presentation(self.request)
        return scope["selected_child"] or models.Child.objects.first()


class BMIChangeChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of BMI change over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_bmi",
    )
    template_name = "reports/bmi_change.html"

    def get_context_data(self, **kwargs):
        context = super(BMIChangeChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        objects = report_entries(
            models.BMI,
            self.request,
            child=child,
            source_weight__isnull=False,
            source_height__isnull=False,
        )
        if objects:
            context["html"], context["js"] = graphs.bmi_change(objects)
        return context


class ChildReportList(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    """
    Listing of available reports for a child.
    """

    model = models.Child
    permission_required = ("core.view_child",)
    template_name = "reports/report_list.html"


class DiaperChangeAmounts(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    """
    Graph of diaper "amounts" - measurements of urine output.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_diaperchange",
    )
    template_name = "reports/diaperchange_amounts.html"

    def get_context_data(self, **kwargs):
        context = super(DiaperChangeAmounts, self).get_context_data(**kwargs)
        child = context["object"]
        changes = report_entries(
            models.DiaperChange, self.request, child=child, amount__gt=0
        )
        if changes and changes.count() > 0:
            context["html"], context["js"] = graphs.diaperchange_amounts(changes)
        return context


class DiaperChangeLifetimesChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of diaper "lifetimes" - time between diaper changes.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_diaperchange",
    )
    template_name = "reports/diaperchange_lifetimes.html"

    def get_context_data(self, **kwargs):
        context = super(DiaperChangeLifetimesChildReport, self).get_context_data(
            **kwargs
        )
        child = context["object"]
        changes = report_entries(models.DiaperChange, self.request, child=child)
        if changes and changes.count() > 1:
            context["html"], context["js"] = graphs.diaperchange_lifetimes(changes)
        return context


class DiaperChangeTypesChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of diaper changes by day and type.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_diaperchange",
    )
    template_name = "reports/diaperchange_types.html"

    def get_context_data(self, **kwargs):
        context = super(DiaperChangeTypesChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        changes = report_entries(models.DiaperChange, self.request, child=child)
        if changes:
            context["html"], context["js"] = graphs.diaperchange_types(changes)
        return context


class DiaperChangeIntervalsChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of diaper change intervals.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_diaperchange",
    )
    template_name = "reports/diaperchange_intervals.html"

    def get_context_data(self, **kwargs):
        context = super(DiaperChangeIntervalsChildReport, self).get_context_data(
            **kwargs
        )
        child = context["object"]
        changes = report_entries(models.DiaperChange, self.request, child=child)
        if changes:
            context["html"], context["js"] = graphs.diaperchange_intervals(changes)
        return context


class FeedingAmountsChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of daily feeding amounts over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_feeding",
    )
    template_name = "reports/feeding_amounts.html"

    def __init__(self):
        super(FeedingAmountsChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(FeedingAmountsChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Feeding, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.feeding_amounts(instances)
        return context


class FeedingDurationChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of feeding durations over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_feeding",
    )
    template_name = "reports/feeding_duration.html"

    def __init__(self):
        super(FeedingDurationChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(FeedingDurationChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Feeding, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.feeding_duration(instances)
        return context


class FeedingIntervalsChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of diaper change intervals.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_feeding",
    )
    template_name = "reports/feeding_intervals.html"

    def get_context_data(self, **kwargs):
        context = super(FeedingIntervalsChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Feeding, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.feeding_intervals(instances)
        return context


class FeedingPatternChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of feeding pattern.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_feeding",
    )
    template_name = "reports/feeding_pattern.html"

    def __init__(self):
        super(FeedingPatternChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(FeedingPatternChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Feeding, self.request, child=child).order_by(
            "start"
        )
        if instances:
            context["html"], context["js"] = graphs.feeding_pattern(instances)
        return context


class HeadCircumferenceChangeChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of head circumference change over time, optionally against the WHO
    percentiles for boys or girls.
    """

    def __init__(
        self, sex=None, target_url="reports:report-head-circumference-change-child"
    ) -> None:
        self.model = models.Child
        self.permission_required = (
            "core.view_child",
            "core.view_headcircumference",
        )
        self.template_name = "reports/head_circumference_change.html"
        self.sex = sex
        self.target_url = target_url

    def get_context_data(self, **kwargs):
        context = super(HeadCircumferenceChangeChildReport, self).get_context_data(
            **kwargs
        )
        child = context["object"]
        objects = report_entries(models.HeadCircumference, self.request, child=child)
        percentiles = models.HeadCircumferencePercentile.objects.filter(sex=self.sex)
        context["target_url"] = self.target_url
        if objects:
            context["html"], context["js"] = graphs.head_circumference_change(
                objects, percentiles, child.corrected_birth_date
            )
        return context


class HeadCircumferenceChangeChildBoyReport(HeadCircumferenceChangeChildReport):
    def __init__(self):
        super().__init__(
            sex="boy",
            target_url="reports:report-head-circumference-change-child-boy",
        )


class HeadCircumferenceChangeChildGirlReport(HeadCircumferenceChangeChildReport):
    def __init__(self):
        super().__init__(
            sex="girl",
            target_url="reports:report-head-circumference-change-child-girl",
        )


class HeightChangeChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of height change over time.
    """

    def __init__(
        self, sex=None, target_url="reports:report-height-change-child"
    ) -> None:
        self.model = models.Child
        self.permission_required = (
            "core.view_child",
            "core.view_height",
        )
        self.template_name = "reports/height_change.html"
        self.sex = sex
        self.target_url = target_url

    def get_context_data(self, **kwargs):
        context = super(HeightChangeChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        birthday = child.corrected_birth_date
        actual_heights = report_entries(models.Height, self.request, child=child)
        percentile_heights = models.HeightPercentile.objects.filter(sex=self.sex)
        context["target_url"] = self.target_url
        if actual_heights:
            context["html"], context["js"] = graphs.height_change(
                actual_heights, percentile_heights, birthday
            )
        return context


class HeightChangeChildBoyReport(HeightChangeChildReport):
    def __init__(self):
        super(HeightChangeChildBoyReport, self).__init__(
            sex="boy", target_url="reports:report-height-change-child-boy"
        )


class HeightChangeChildGirlReport(HeightChangeChildReport):
    def __init__(self):
        super(HeightChangeChildGirlReport, self).__init__(
            sex="girl", target_url="reports:report-height-change-child-girl"
        )


class PumpingAmounts(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    """
    Graph of pumping milk amounts collected.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_pumping",
    )
    template_name = "reports/pumping_amounts.html"

    def get_context_data(self, **kwargs):
        context = super(PumpingAmounts, self).get_context_data(**kwargs)
        child = context["object"]
        changes = report_entries(models.Pumping, self.request, child=child)
        if changes and changes.count() > 0:
            context["html"], context["js"] = graphs.pumping_amounts(changes)
        return context


class ActivityPatternChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Day-by-day chart of all activities for the last N days (#218, #881).
    """

    model = models.Child
    permission_required = ("core.view_child",)
    template_name = "reports/activity_pattern.html"
    default_days = 14

    def get_context_data(self, **kwargs):
        from reports.graphs.activity_pattern import block_label

        context = super().get_context_data(**kwargs)
        child = context["object"]
        user = self.request.user
        period = report_period(self.request)
        if not period.is_valid():
            return context
        first_day = period.cleaned_data.get("range_start")
        last_day = period.cleaned_data.get("range_end")
        if (
            not first_day
            and "period" not in self.request.GET
            and "days" in self.request.GET
        ):
            try:
                days = max(1, min(int(self.request.GET["days"]), 90))
            except (ValueError, TypeError):
                days = self.default_days
            last_day = timezone.localdate()
            first_day = last_day - timezone.timedelta(days=days - 1)

        intervals, points, labels = [], [], {}
        interval_models = (
            ("sleep", models.Sleep, _("Sleep")),
            ("feeding", models.Feeding, _("Feeding")),
            ("tummytime", models.TummyTime, _("Tummy Time")),
            ("pumping", models.Pumping, _("Pumping")),
        )
        for kind, model, name in interval_models:
            if not user.has_perm(
                f"{model._meta.app_label}.view_{model._meta.model_name}"
            ):
                continue
            labels[kind] = name
            from django.db.models import Q

            entries = model.objects.filter(child=child)
            if first_day:
                entries = entries.filter(start__date__lte=last_day).filter(
                    Q(end__date__gte=first_day)
                    | Q(end__isnull=True, start__date__gte=first_day)
                )
            for instance in entries.order_by("start"):
                end = instance.end or instance.start
                if end == instance.start:
                    # An instant (e.g. a bottle feed) is drawn as a short block.
                    end = end + timezone.timedelta(minutes=5)
                intervals.append(
                    (kind, instance.start, end, block_label(name, instance.start, end))
                )
        if user.has_perm("core.view_diaperchange"):
            labels["diaperchange"] = _("Diaper Change")
            for instance in report_entries(
                models.DiaperChange, self.request, child=child
            ):
                points.append(
                    (
                        "diaperchange",
                        instance.time,
                        "{}: {}".format(
                            _("Diaper Change"),
                            ", ".join(str(a) for a in instance.attributes()),
                        ),
                    )
                )
        if user.has_perm("core.view_medication"):
            labels["medication"] = _("Medication")
            for instance in report_entries(
                models.Medication, self.request, child=child
            ):
                points.append(("medication", instance.time, instance.name))

        if intervals or points:
            dates = [
                timezone.localtime(value).date()
                for _, start, end, _ in intervals
                for value in (start, end)
            ]
            dates.extend(timezone.localtime(value).date() for _, value, _ in points)
            first_day = first_day or min(dates)
            last_day = last_day or max(dates)
            context["html"], context["js"] = graphs.activity_pattern(
                intervals, points, first_day, last_day, labels
            )
        return context


class SleepPatternChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of sleep pattern comparing sleep to wake times by day.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_sleep",
    )
    template_name = "reports/sleep_pattern.html"

    def __init__(self):
        super(SleepPatternChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(SleepPatternChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Sleep, self.request, child=child).order_by(
            "start"
        )
        if instances:
            context["html"], context["js"] = graphs.sleep_pattern(instances)
        return context


class SleepTotalsChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of total sleep by day.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_sleep",
    )
    template_name = "reports/sleep_totals.html"

    def __init__(self):
        super(SleepTotalsChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(SleepTotalsChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Sleep, self.request, child=child).order_by(
            "start"
        )
        if instances:
            context["html"], context["js"] = graphs.sleep_totals(instances)
        return context


class TemperatureChangeChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of temperature change over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_temperature",
    )
    template_name = "reports/temperature_change.html"

    def get_context_data(self, **kwargs):
        context = super(TemperatureChangeChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        objects = report_entries(models.Temperature, self.request, child=child)
        if objects:
            context["html"], context["js"] = graphs.temperature_change(objects)
        return context


class TummyTimeDurationChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of tummy time durations over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_tummytime",
    )
    template_name = "reports/tummytime_duration.html"

    def __init__(self):
        super(TummyTimeDurationChildReport, self).__init__()
        self.html = ""
        self.js = ""

    def get_context_data(self, **kwargs):
        context = super(TummyTimeDurationChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.TummyTime, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.tummytime_duration(instances)
        return context


class WeightChangeChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of weight change over time.
    """

    def __init__(
        self, sex=None, target_url="reports:report-weight-change-child"
    ) -> None:
        self.model = models.Child
        self.permission_required = (
            "core.view_child",
            "core.view_weight",
        )
        self.template_name = "reports/weight_change.html"
        self.sex = sex
        self.target_url = target_url

    def get_context_data(self, **kwargs):
        context = super(WeightChangeChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        birthday = child.corrected_birth_date
        actual_weights = report_entries(models.Weight, self.request, child=child)
        percentile_weights = models.WeightPercentile.objects.filter(sex=self.sex)
        context["target_url"] = self.target_url
        if actual_weights:
            context["html"], context["js"] = graphs.weight_change(
                actual_weights, percentile_weights, birthday
            )
        return context


class WeightChangeChildBoyReport(WeightChangeChildReport):
    def __init__(self):
        super(WeightChangeChildBoyReport, self).__init__(
            sex="boy", target_url="reports:report-weight-change-child-boy"
        )


class WeightChangeChildGirlReport(WeightChangeChildReport):
    def __init__(self):
        super(WeightChangeChildGirlReport, self).__init__(
            sex="girl", target_url="reports:report-weight-change-child-girl"
        )


class MedicationFrequencyChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of medication frequency over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_medication",
    )
    template_name = "reports/medication_frequency.html"

    def get_context_data(self, **kwargs):
        context = super(MedicationFrequencyChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Medication, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.medication_frequency(instances)
        return context


class MedicationIntervalsChildReport(
    ReportPresentationMixin, PermissionRequiredMixin, DetailView
):
    """
    Graph of medication intervals over time.
    """

    model = models.Child
    permission_required = (
        "core.view_child",
        "core.view_medication",
    )
    template_name = "reports/medication_intervals.html"

    def get_context_data(self, **kwargs):
        context = super(MedicationIntervalsChildReport, self).get_context_data(**kwargs)
        child = context["object"]
        instances = report_entries(models.Medication, self.request, child=child)
        if instances:
            context["html"], context["js"] = graphs.medication_intervals(instances)
        return context
