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
)
from core.utils import duration_string

from django.db.models import Q, F, OuterRef, Prefetch, Subquery
from core.units import entry_value


def _date_range(field, start, end):
    return Q(**{field + "__range": (start, end)}) if start is not None else Q()


def _in_range(value, start, end):
    return start is None or start <= value <= end


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
        _add_feedings(min_date, max_date, events, child)
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
        _add_foods(min_date, max_date, events, child)

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
    instances = TummyTime.objects.filter(
        _date_range("start", min_date, max_date)
        | _date_range("end", min_date, max_date)
    ).order_by("-start")
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.milestone:
            details.append(instance.milestone)
        if instance.notes:
            details.append(instance.notes)
        edit_link = reverse("core:tummytime-update", args=[instance.id])
        if _in_range(instance.start, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.start),
                    "event": _("%(child)s started tummy time!")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start",
                    "tags": instance.timeline_tags,
                }
            )

        if _in_range(instance.end, min_date, max_date):
            end = {
                "time": timezone.localtime(instance.end),
                "event": _("%(child)s finished tummy time.")
                % {"child": instance.child.first_name},
                "details": details,
                "edit_link": edit_link,
                "model_name": instance.model_name,
                "type": "end",
                "tags": instance.timeline_tags,
            }
            if instance.duration > timedelta(seconds=0):
                end["duration"] = duration_string(instance.duration)

            events.append(end)


def _add_sleeps(min_date, max_date, events, child=None):
    instances = Sleep.objects.filter(
        _date_range("start", min_date, max_date)
        | _date_range("end", min_date, max_date)
    ).order_by("-start")
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.notes:
            details.append(instance.notes)
        edit_link = reverse("core:sleep-update", args=[instance.id])
        if _in_range(instance.start, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.start),
                    "event": _("%(child)s fell asleep.")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start",
                    "tags": instance.timeline_tags,
                }
            )

        if _in_range(instance.end, min_date, max_date):
            end = {
                "time": timezone.localtime(instance.end),
                "event": _("%(child)s woke up.") % {"child": instance.child.first_name},
                "details": details,
                "edit_link": edit_link,
                "model_name": instance.model_name,
                "type": "end",
                "tags": instance.timeline_tags,
            }
            if instance.duration > timedelta(seconds=0):
                end["duration"] = duration_string(instance.duration)
            events.append(end)


def _add_feedings(min_date, max_date, events, child=None):
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
            _date_range("start", min_date, max_date)
            | _date_range("end", min_date, max_date)
        )
        .annotate(previous_start=Subquery(previous.values("start")[:1]))
        .order_by("start", "pk")
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = []
        if instance.notes:
            details.append(instance.notes)
        time_since_prev = None
        if instance.previous_start:
            time_since_prev = timesince.timesince(
                instance.previous_start, now=instance.start
            )
        edit_link = reverse("core:feeding-update", args=[instance.id])
        if instance.total_amount:
            details.append(
                _("Amount")
                + ": "
                + (
                    entry_value(instance, "total_amount")
                    if instance.entry_unit
                    else instance.amount_display
                )
            )
        if instance.secondary_type:
            details.append(instance.type_display)

        base_object = {
            "time": timezone.localtime(instance.start),
            "details": details,
            "edit_link": edit_link,
            "model_name": instance.model_name,
            "tags": instance.timeline_tags,
        }

        if instance.duration > timedelta(seconds=0):
            if _in_range(instance.start, min_date, max_date):
                start_event = {
                    **base_object,
                    "event": _("%(child)s started feeding.")
                    % {"child": instance.child.first_name},
                    "time_since_prev": time_since_prev,
                    "type": "start",
                }
                events.append(start_event)

            if _in_range(instance.end, min_date, max_date):
                end_event = {
                    **base_object,
                    "time": timezone.localtime(instance.end),
                    "event": _("%(child)s finished feeding.")
                    % {"child": instance.child.first_name},
                    "type": "end",
                    "duration": duration_string(instance.duration),
                }

                events.append(end_event)
        else:
            if _in_range(instance.start, min_date, max_date):
                feed_event = {
                    **base_object,
                    "event": _("%(child)s had a feeding.")
                    % {"child": instance.child.first_name},
                    "time_since_prev": time_since_prev,
                }
                events.append(feed_event)


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
    instances = BathTime.objects.filter(
        _date_range("start", min_date, max_date)
        | _date_range("end", min_date, max_date)
    ).order_by("-start")
    if child:
        instances = instances.filter(child=child)
    for instance in instances.select_related("child").prefetch_related(
        Prefetch("tags", to_attr="timeline_tags")
    ):
        details = [instance.notes] if instance.notes else []
        edit_link = reverse("core:bathtime-update", args=[instance.id])
        if _in_range(instance.start, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.start),
                    "event": _("%(child)s started a bath.")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start",
                    "tags": instance.timeline_tags,
                }
            )
        if _in_range(instance.end, min_date, max_date):
            end = {
                "time": timezone.localtime(instance.end),
                "event": _("%(child)s finished a bath.")
                % {"child": instance.child.first_name},
                "details": details,
                "edit_link": edit_link,
                "model_name": instance.model_name,
                "type": "end",
                "tags": instance.timeline_tags,
            }
            if instance.duration and instance.duration > timedelta(seconds=0):
                end["duration"] = duration_string(instance.duration)
            events.append(end)


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


def _add_foods(min_date, max_date, events, child=None):
    instances = Food.objects.filter(_date_range("time", min_date, max_date)).order_by(
        "-time"
    )
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
        Pumping.objects.filter(_date_range("start", min_date, max_date))
        .select_related("child")
        .prefetch_related(Prefetch("tags", to_attr="timeline_tags"))
    )
    if child:
        entries = entries.filter(child=child)
    for entry in entries:
        events.append(
            {
                "time": timezone.localtime(entry.start),
                "event": _("Pumping"),
                "details": [entry_value(entry, "amount")]
                + ([entry.notes] if entry.notes else []),
                "duration": duration_string(entry.duration) if entry.duration else None,
                "edit_link": reverse("core:pumping-update", args=[entry.pk]),
                "model_name": "pumping",
                "tags": entry.timeline_tags,
            }
        )
