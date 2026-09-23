# -*- coding: utf-8 -*-
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic.detail import DetailView
from django.views.generic.base import TemplateView

from babybuddy.mixins import PermissionRequiredMixin
from core import models

from . import graphs


def report_period(request):
    from core.forms import RecordPeriodFilterForm

    if not hasattr(request, "_report_period"):
        request._report_period = RecordPeriodFilterForm(request.GET, user=request.user)
        request._report_period.is_valid()
    return request._report_period


def report_entries(model, request, include_top_ups=False, **filters):
    from datetime import date
    from django.db.models import DateTimeField, DateField, Q

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
            bounds = Q(**{lookup + "__gte": first, lookup + "__lte": last})
            if include_top_ups:
                bounds |= Q(top_up_at__date__gte=first, top_up_at__date__lte=last)
            queryset = queryset.filter(bounds)
        elif "period" not in request.GET:
            # Existing bookmarked ranges remain valid until a period is chosen.
            for parameter, operation in (("from", "gte"), ("to", "lte")):
                try:
                    value = date.fromisoformat(request.GET.get(parameter, ""))
                except ValueError:
                    continue
                bounds = Q(**{lookup + "__" + operation: value})
                if include_top_ups:
                    bounds |= Q(**{"top_up_at__date__" + operation: value})
                queryset = queryset.filter(bounds)
    return queryset


def report_unit_context(request, metric):
    from core.units import SPECS, preferred_unit

    if metric not in SPECS:
        return {}
    choices = SPECS[metric][3]
    unit = request.GET.get("unit", preferred_unit(request.user.settings, metric))
    if unit not in dict(choices):
        unit = preferred_unit(request.user.settings, metric)
    return {"report_unit": unit, "report_unit_choices": choices}


def known_unit_entries(objects, context, metric):
    from core.units import SPECS

    choices = dict(SPECS[metric][3])
    context["unknown_unit_count"] = objects.exclude(entry_unit__in=choices).count()
    return objects.filter(entry_unit__in=choices)


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
            not getattr(self, "household_report", False)
            and not scope["selected_child"]
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
        if self.request.headers.get("X-Report-Partial") == "1":
            from django.http import JsonResponse
            from django.template.loader import render_to_string
            from django.templatetags.static import static
            from reports.utils import plot_payloads

            context["report_shell"] = "reports/fragment.html"
            plots = []
            for panel in context.get("report_panels") or [context]:
                plots.extend(plot_payloads(panel.get("js", "")))
            return JsonResponse(
                {
                    "html": render_to_string(
                        self.get_template_names(), context, request=self.request
                    ),
                    "plots": plots,
                    "household_page": bool(getattr(self, "household_report", False)),
                    "plotly_url": static("babybuddy/js/graph.js")
                    + "?v=20260921-security",
                }
            )
        return super().render_to_response(context, **response_kwargs)


class ReportsHome(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    model = models.Child
    permission_required = ("core.view_child",)
    template_name = "reports/report_list.html"

    def get_object(self, queryset=None):
        from core.presentation import presentation

        scope = presentation(self.request)
        return scope["selected_child"] or models.Child.objects.first()


class GrowthReport(ReportPresentationMixin, PermissionRequiredMixin, DetailView):
    model = models.Child
    permission_required = ("core.view_child",)
    template_name = "reports/growth.html"
    metric = "weight"
    sex = None

    def get_metric(self):
        from reports.growth import METRICS

        metric = self.request.GET.get("metric", self.metric)
        return metric if metric in METRICS else self.metric

    def get_permission_required(self):
        from reports.growth import PERMISSIONS

        return ("core.view_child", PERMISSIONS[self.get_metric()])

    def get_context_data(self, **kwargs):
        from reports.growth import METRICS, PERMISSIONS, growth_chart

        context = super().get_context_data(**kwargs)
        metric = self.get_metric()
        model, field, percentile_model, label = METRICS[metric]
        child = context["object"]
        objects = report_entries(model, self.request, child=child)
        if metric == "bmi":
            objects = objects.filter(
                source_weight__isnull=False, source_height__isnull=False
            )
        else:
            objects = known_unit_entries(objects, context, metric)
        context.update(report_unit_context(self.request, metric))
        refs = (
            self.request.GET.getlist("reference")
            if "reference_controls" in self.request.GET
            else ([self.sex] if self.sex else ["boy", "girl"])
        )
        context.update(
            growth_metric=metric,
            growth_label=label,
            growth_references=refs,
            growth_percentiles=self.request.GET.get("percentiles") == "1",
            corrected_age=child.is_premature,
        )
        links = []
        for key, spec in METRICS.items():
            if self.request.user.has_perm(PERMISSIONS[key]):
                query = self.request.GET.copy()
                query["metric"] = key
                query.pop("unit", None)
                links.append((key, spec[3], query.urlencode()))
        context["growth_links"] = links
        html, js = growth_chart(
            objects,
            child,
            metric,
            context.get("report_unit", ""),
            refs,
            percentiles=context["growth_percentiles"],
        )
        if html:
            context.update(html=html, js=js)
        return context


class BMIChangeChildReport(GrowthReport):
    metric = "bmi"


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
        changes = report_entries(models.DiaperChange, self.request, child=child)
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
        instances = report_entries(
            models.Feeding, self.request, child=child, include_top_ups=True
        )
        instances = known_unit_entries(instances, context, "feeding")
        context.update(report_unit_context(self.request, "feeding"))
        context["feeding_group"] = (
            "session" if self.request.GET.get("group") == "session" else "type"
        )
        period = report_period(self.request)
        first = period.cleaned_data.get("range_start")
        last = period.cleaned_data.get("range_end")
        if not first and "period" not in self.request.GET:
            from datetime import date

            for parameter in ("from", "to"):
                try:
                    value = date.fromisoformat(self.request.GET.get(parameter, ""))
                    if parameter == "from":
                        first = value
                    else:
                        last = value
                except ValueError:
                    pass
        if instances:
            context["html"], context["js"] = graphs.feeding_amounts(
                instances,
                unit=context["report_unit"],
                group=context["feeding_group"],
                first_day=first,
                last_day=last,
                use_24_hour=self.request.user.settings.use_24_hour_time,
            )
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
        from django.db.models import Q

        period = report_period(self.request)
        if not period.is_valid():
            return context
        first = period.cleaned_data.get("range_start")
        last = period.cleaned_data.get("range_end")
        if first:
            instances = (
                models.Feeding.objects.filter(child=child, start__date__lte=last)
                .filter(
                    Q(end__date__gte=first)
                    | Q(end__isnull=True, start__date__gte=first)
                )
                .order_by("start")
            )
        else:
            instances = report_entries(
                models.Feeding, self.request, child=child
            ).order_by("start")
        if instances:
            context["html"], context["js"] = graphs.feeding_pattern(
                instances,
                first_day=first,
                last_day=last,
                use_24_hour=self.request.user.settings.use_24_hour_time,
            )
        return context


class HeadCircumferenceChangeChildReport(GrowthReport):
    metric = "headcircumference"


class HeadCircumferenceChangeChildBoyReport(HeadCircumferenceChangeChildReport):
    sex = "boy"


class HeadCircumferenceChangeChildGirlReport(HeadCircumferenceChangeChildReport):
    sex = "girl"


class HeightChangeChildReport(GrowthReport):
    metric = "height"


class HeightChangeChildBoyReport(HeightChangeChildReport):
    sex = "boy"


class HeightChangeChildGirlReport(HeightChangeChildReport):
    sex = "girl"


class PumpingAmounts(ReportPresentationMixin, PermissionRequiredMixin, TemplateView):
    permission_required = ("core.view_pumping",)
    template_name = "reports/pumping_amounts.html"
    household_report = True

    def get_context_data(self, **kwargs):
        from types import SimpleNamespace
        from core.lactation import sessions

        context = super().get_context_data(**kwargs)
        context["household_page"] = True
        context["pumping_view"] = (
            "amounts"
            if self.request.GET.get(
                "view", "amounts" if "slug" in self.kwargs else "pattern"
            )
            == "amounts"
            else "pattern"
        )
        period = report_period(self.request)
        if not period.is_valid():
            return context
        pumps, nursing = sessions(self.request.user)
        first, last = context["report_range_start"], context["report_range_end"]
        if context["pumping_view"] == "amounts":
            changes = report_entries(models.Pumping, self.request).filter(
                pk__in=pumps.values("pk")
            )
            changes = known_unit_entries(changes, context, "pumping")
            context.update(report_unit_context(self.request, "pumping"))
            if changes:
                context["html"], context["js"] = graphs.pumping_amounts(
                    changes, unit=context["report_unit"]
                )
        else:
            if first:
                pumps = pumps.filter(start__date__lte=last, end__date__gte=first)
                nursing = nursing.filter(start__date__lte=last, end__date__gte=first)
            else:
                pumps = pumps.filter(
                    pk__in=report_entries(models.Pumping, self.request).values("pk")
                )
                nursing = nursing.filter(
                    pk__in=report_entries(models.Feeding, self.request).values("pk")
                )
            entries = []
            methods = [
                ("pump-left", _("Pumping · left")),
                ("pump-right", _("Pumping · right")),
                ("pump-both", _("Pumping · both")),
                ("pump-unknown", _("Pumping · side not recorded")),
                ("left breast", _("Nursing · left")),
                ("right breast", _("Nursing · right")),
                ("both breasts", _("Nursing · both")),
            ]
            for entry in pumps:
                entries.append(
                    SimpleNamespace(
                        pk=f"pump-{entry.pk}",
                        start=entry.start,
                        end=entry.end,
                        method="pump-" + (entry.side or "unknown"),
                    )
                )
            for entry in nursing:
                entries.append(
                    SimpleNamespace(
                        pk=f"nurse-{entry.pk}",
                        start=entry.start,
                        end=entry.end,
                        method=entry.method,
                    )
                )
            context["html"], context["js"] = graphs.feeding_pattern(
                entries,
                first_day=first,
                last_day=last,
                use_24_hour=self.request.user.settings.use_24_hour_time,
                session_methods=methods,
            )
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
                intervals.append(
                    (
                        kind,
                        instance.start,
                        end,
                        block_label(
                            name, instance.start, end, user.settings.use_24_hour_time
                        ),
                    )
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
                intervals,
                points,
                first_day,
                last_day,
                labels,
                use_24_hour=user.settings.use_24_hour_time,
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
        period = report_period(self.request)
        if not period.is_valid():
            return context
        first = period.cleaned_data.get("range_start")
        last = period.cleaned_data.get("range_end")
        if first:
            instances = models.Sleep.objects.filter(
                child=child, start__date__lte=last, end__date__gte=first
            ).order_by("start")
        else:
            instances = report_entries(
                models.Sleep, self.request, child=child
            ).order_by("start")
        if instances:
            context["html"], context["js"] = graphs.sleep_pattern(
                instances,
                first_day=first,
                last_day=last,
                use_24_hour=self.request.user.settings.use_24_hour_time,
            )
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
        objects = known_unit_entries(objects, context, "temperature")
        context.update(report_unit_context(self.request, "temperature"))
        if objects:
            context["html"], context["js"] = graphs.temperature_change(
                objects, unit=context["report_unit"]
            )
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


class WeightChangeChildReport(GrowthReport):
    metric = "weight"


class WeightChangeChildBoyReport(WeightChangeChildReport):
    sex = "boy"


class WeightChangeChildGirlReport(WeightChangeChildReport):
    sex = "girl"


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
