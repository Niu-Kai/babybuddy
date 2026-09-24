# -*- coding: utf-8 -*-
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone, timesince
from django.utils.translation import gettext as _

from core.models import (
    BathTime,
    Food,
    Reflux,
    DiaperChange,
    Feeding,
    Pumping,
    Note,
    Sleep,
    TummyTime,
    Temperature,
    Medication,
    Timer,
)
from core.utils import duration_string, timezone_aware_duration

from django.db.models import Q, F, OuterRef, Prefetch, Subquery
from core.units import entry_value


def _date_range(field, start, end):
    return Q(**{field + "__range": (start, end)}) if start is not None else Q()


def _in_range(value, start, end):
    return start is None or start <= value <= end


def _session_range(start, end):
    """Include sessions overlapping the period, including an entire middle day.

    Missing end times on saved entries mean no duration, not an ongoing timer.
    """
    if start is None:
        return Q()
    return Q(start__lte=end) & (Q(end__gt=start) | Q(start__gte=start))


def _session_event(instance, label, details):
    start = timezone.localtime(instance.start)
    end = timezone.localtime(instance.end) if instance.end else None
    duration = getattr(instance, "duration", None)
    if duration is None and instance.end:
        duration = timezone_aware_duration(instance.start, instance.end)
    return {
        "time": start,
        "session_start": start,
        "session_end": end if end and duration and duration > timedelta(0) else None,
        "clock_change": bool(end and start.utcoffset() != end.utcoffset()),
        "event": (
            f"{instance.child.first_name} · {label}" if instance.child_id else label
        ),
        "details": details,
        "duration": duration_string(duration) if duration else None,
        "edit_link": reverse(f"core:{instance.model_name}-update", args=[instance.pk]),
        "model_name": instance.model_name,
        "tags": getattr(instance, "timeline_tags", []),
    }


def get_objects(date=None, child=None, user=None, activity="", end_date=None):
    """
    Create a time-sorted dictionary of all events for a child.
    :param date: optional local DateTime for one day; None includes all history.
    :param end_date: optional inclusive end of a calendar range.
    :param child: Child instance to filter results for (no filter if `None`).
    :param user: User the timeline is rendered for. Event types the user has no
        `view` permission for are left out. All types are included if `None`.
    :returns: events ordered newest first.
    """
    min_date = date.replace(hour=0, minute=0, second=0, microsecond=0) if date else None
    max_date = (
        (end_date or date).replace(hour=23, minute=59, second=59, microsecond=999999)
        if date
        else None
    )
    events = []

    def permitted(model_name):
        return (not activity or activity == model_name) and (
            user is None or user.has_perm(f"core.view_{model_name}")
        )

    if permitted("diaperchange"):
        _add_diaper_changes(min_date, max_date, events, child)
    if permitted("feeding"):
        _add_feedings(
            min_date,
            max_date,
            events,
            child,
            user is None or user.has_perm("core.view_food"),
        )
    if permitted("pumping"):
        _add_pumpings(min_date, max_date, events, child)
    if permitted("medication"):
        _add_medication(min_date, max_date, events, child)
    if permitted("sleep"):
        _add_sleeps(min_date, max_date, events, child)
    if permitted("tummytime"):
        _add_tummy_times(min_date, max_date, events, child)
    if permitted("note"):
        _add_notes(min_date, max_date, events, child)
    if permitted("temperature"):
        _add_temperature_measurements(min_date, max_date, events, child)
    if permitted("bathtime"):
        _add_bathtimes(min_date, max_date, events, child)
    if permitted("reflux"):
        _add_reflux(min_date, max_date, events, child)
    if permitted("food"):
        _add_foods(
            min_date, max_date, events, child, include_linked=not permitted("feeding")
        )

    if permitted("customactivity"):
        from core.models import CustomActivity

        entries = CustomActivity.objects.filter(
            _session_range(min_date, max_date)
        ).select_related("child", "activity_type")
        if child:
            entries = entries.filter(child=child)
        for entry in entries:
            details = [entry.choice, entry.text, entry.notes]
            if entry.amount is not None:
                details.append(
                    f"{entry.activity_type.amount_label}: {entry.amount:g} {entry.activity_type.amount_unit}"
                )
            if entry.activity_type.check_label:
                details.append(
                    f"{entry.activity_type.check_label}: {'Yes' if entry.checked else 'No'}"
                )
            events.append(
                _session_event(
                    entry, entry.activity_type.name, [d for d in details if d]
                )
            )

    if user is not None and user.has_perm("core.view_timer"):
        _add_active_timers(min_date, max_date, events, child, user, permitted)

    explicit_type_ordering = {"start": 0, "end": 1}
    events.sort(
        key=lambda x: (
            x["time"],
            explicit_type_ordering.get(x.get("type"), -1),
        ),
        reverse=True,
    )

    return events


def _add_tummy_times(min_date, max_date, events, child=None):
    instances = TummyTime.objects.filter(_session_range(min_date, max_date)).order_by(
        "-start"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = ([instance.milestone] if instance.milestone else []) + (
            [instance.notes] if instance.notes else []
        )
        events.append(_session_event(instance, _("Tummy time"), details))


def _add_sleeps(min_date, max_date, events, child=None):
    instances = Sleep.objects.filter(_session_range(min_date, max_date)).order_by(
        "-start"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = [instance.notes] if instance.notes else []
        events.append(_session_event(instance, _("Sleep"), details))


def _add_feedings(min_date, max_date, events, child=None, show_foods=True):
    previous = (
        Feeding.objects.filter(child_id=OuterRef("child_id"))
        .filter(
            Q(start__lt=OuterRef("start"))
            | Q(start=OuterRef("start"), pk__lt=OuterRef("pk"))
        )
        .order_by("-start", "-pk")
    )
    instances = (
        Feeding.objects.filter(
            _session_range(min_date, max_date)
            | _date_range("top_up_at", min_date, max_date)
        )
        .annotate(previous_start=Subquery(previous.values("start")[:1]))
        .order_by("start", "pk")
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags"), "foods"
    ):
        details = []
        if show_foods:
            for food in instance.foods.all():
                details.append(
                    food.name
                    + (" · " + food.get_reaction_display() if food.reaction else "")
                )
        if instance.notes:
            details.append(instance.notes)
        time_since_prev = None
        if instance.previous_start:
            time_since_prev = timesince.timesince(
                instance.previous_start, now=instance.start
            )
        if not instance.top_up_at and instance.total_amount:
            details.append(
                _("Amount")
                + ": "
                + (
                    entry_value(instance, "total_amount")
                    if instance.entry_unit
                    else instance.amount_display
                )
            )
        details.append(
            " · ".join(
                filter(None, [instance.type_display, instance.get_method_display()])
            )
        )

        event = _session_event(instance, _("Feeding"), details)
        event["time_since_prev"] = time_since_prev
        if instance.top_up_at:
            from core.top_ups import top_up_summary

            event["top_up_at"] = timezone.localtime(instance.top_up_at)
            event["top_up_summary"] = top_up_summary(instance)
        events.append(event)


def _add_diaper_changes(min_date, max_date, events, child):
    instances = DiaperChange.objects.filter(
        _date_range("time", min_date, max_date)
    ).order_by("-time")
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        contents = []
        if instance.wet:
            contents.append("💧")
        if instance.solid:
            contents.append("💩")
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s had a %(type)s diaper change.")
                % {
                    "child": instance.child.first_name,
                    "type": "".join(contents),
                },
                "edit_link": reverse("core:diaperchange-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.timeline_tags,
            }
        )


def _add_medication(min_date, max_date, events, child):
    instances = (
        Medication.objects.annotate(
            db_next_dose_time=F("time") + F("next_dose_interval")
        )
        .filter(
            _date_range("time", min_date, max_date)
            | _date_range("db_next_dose_time", min_date, max_date)
        )
        .order_by("-time")
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.dosage:
            details.append(
                _("Dosage")
                + ": "
                + str(instance.dosage)
                + " "
                + instance.get_dosage_unit_display()
            )
        if instance.notes:
            details.append(instance.notes)
        edit_link = reverse("core:medication-update", args=[instance.id])

        if _in_range(instance.time, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.time),
                    "event": _("%(child)s took %(medication)s.")
                    % {
                        "child": instance.child.first_name,
                        "medication": instance.name,
                    },
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start" if instance.next_dose_time else None,
                    "tags": instance.timeline_tags,
                }
            )
        if instance.next_dose_time and _in_range(
            instance.next_dose_time, min_date, max_date
        ):
            events.append(
                {
                    "time": timezone.localtime(instance.next_dose_time),
                    "event": _("%(child)s's %(medication)s dose wore off.")
                    % {
                        "child": instance.child.first_name,
                        "medication": instance.name,
                    },
                    "details": [],
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "end",
                    "tags": instance.timeline_tags,
                }
            )


def _add_notes(min_date, max_date, events, child):
    instances = Note.objects.filter(_date_range("time", min_date, max_date)).order_by(
        "-time"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "details": [instance.note],
                "edit_link": reverse("core:note-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.timeline_tags,
            }
        )


def _add_temperature_measurements(min_date, max_date, events, child):
    instances = Temperature.objects.filter(
        _date_range("time", min_date, max_date)
    ).order_by("-time")
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.notes:
            details.append(instance.notes)
        if instance.temperature:
            details.append(
                _("Temperature") + ": " + entry_value(instance, "temperature")
            )
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s had a temperature measurement.")
                % {
                    "child": instance.child.first_name,
                },
                "details": details,
                "edit_link": reverse("core:temperature-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.timeline_tags,
            }
        )


def _add_bathtimes(min_date, max_date, events, child=None):
    instances = BathTime.objects.filter(_session_range(min_date, max_date)).order_by(
        "-start"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = [instance.notes] if instance.notes else []
        events.append(_session_event(instance, _("Bath time"), details))


def _add_reflux(min_date, max_date, events, child=None):
    instances = Reflux.objects.filter(_date_range("time", min_date, max_date)).order_by(
        "-time"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = [instance.get_severity_display()]
        if instance.notes:
            details.append(instance.notes)
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s had a reflux episode.")
                % {"child": instance.child.first_name},
                "details": details,
                "edit_link": reverse("core:reflux-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.timeline_tags,
            }
        )


def _add_foods(min_date, max_date, events, child=None, include_linked=True):
    instances = Food.objects.filter(_date_range("time", min_date, max_date)).order_by(
        "-time"
    )
    if not include_linked:
        instances = instances.filter(feeding__isnull=True)
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.amount is not None:
            details.append(_("Amount") + ": " + str(instance.amount))
        if instance.reaction:
            details.append(instance.get_reaction_display())
        if instance.notes:
            details.append(instance.notes)
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s tried %(name)s.")
                % {"child": instance.child.first_name, "name": instance.name},
                "details": details,
                "edit_link": reverse("core:food-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.timeline_tags,
            }
        )


def _add_pumpings(min_date, max_date, events, child):
    if child:
        return
    entries = (
        Pumping.objects.filter(_session_range(min_date, max_date))
        .select_related("child")
        .prefetch_related(Prefetch("tags", to_attr="timeline_tags"))
    )
    for entry in entries:
        event = _session_event(
            entry,
            _("Pumping"),
            [entry_value(entry, "amount")] + ([entry.notes] if entry.notes else []),
        )
        # Pumping is household-level, including older records with a child attached.
        event["event"] = _("Pumping")
        events.append(event)


def _add_active_timers(min_date, max_date, events, child, user, permitted):
    from core.access import scoped

    activities = [
        name
        for name in ("feeding", "sleep", "pumping", "tummytime", "bathtime")
        if permitted(name)
    ]
    if not activities:
        return
    now = timezone.now()
    if min_date and min_date > now:
        return
    timers = scoped(
        Timer.objects.filter(
            active=True, start__lte=now, context__activity__in=activities
        ),
        user,
    )
    if max_date:
        timers = timers.filter(start__lte=max_date)
    if child:
        timers = timers.filter(child=child).exclude(context__activity="pumping")
    for timer in timers.select_related("child"):
        activity = timer.context.get("activity")
        # Unassigned generic timers cannot be attributed to a child activity yet.
        if not timer.child_id and activity != "pumping":
            continue
        start = timezone.localtime(timer.start)
        events.append(
            {
                "time": start,
                "session_start": start,
                "event": (
                    timer.title_with_child if activity != "pumping" else str(timer)
                ),
                "details": [],
                "duration": duration_string(timer.duration(), precision="m"),
                "in_progress": True,
                "paused": timer.paused_at is not None,
                "edit_link": reverse("core:timer-detail", args=[timer.pk]),
                "model_name": activity,
                "tags": [],
            }
        )
