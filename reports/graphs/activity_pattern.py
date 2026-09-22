"""Day/time activity chart with separate lanes for each activity type."""

from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core.utils import duration_string
from reports import utils
from reports.graphs.day_grid import clock, day_layout, wrap_day_chart

COLORS = {
    "sleep": "#6487a7",
    "feeding": "#b28e6c",
    "tummytime": "#71978b",
    "pumping": "#8f80a7",
}
MARKERS = {"diaperchange": ("#ad7e89", "diamond"), "medication": ("#a29b72", "square")}
MINUTES_PER_DAY = 1440


def _minutes(moment):
    return moment.hour * 60 + moment.minute + moment.second / 60


def _split_by_day(start, end):
    """Yield (date, start, end) for the local-day pieces of an interval."""
    start = timezone.localtime(start)
    end = timezone.localtime(end)
    while start.date() < end.date():
        midnight = (start + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        yield start.date(), start, midnight
        start = midnight
    yield start.date(), start, end


def activity_pattern(intervals, points, first_day, last_day, labels, use_24_hour=False):
    kinds = [
        kind
        for kind in list(COLORS) + list(MARKERS)
        if kind in labels
        and (
            any(item[0] == kind for item in intervals)
            or any(item[0] == kind for item in points)
        )
    ]
    if not kinds:
        return None, None
    days = [
        first_day + timedelta(days=index)
        for index in range((last_day - first_day).days + 1)
    ]
    lane_width = 0.84 / len(kinds)

    def lane_date(day, kind):
        offset = (kinds.index(kind) - (len(kinds) - 1) / 2) * lane_width
        return (day - first_day).days + offset

    traces = []
    for kind in kinds:
        xs, bases, heights, text = [], [], [], []
        px, py, ptext = [], [], []
        for activity, start, end, message in intervals:
            if activity != kind:
                continue
            if end == start:
                moment = timezone.localtime(start)
                if first_day <= moment.date() <= last_day:
                    px.append(lane_date(moment.date(), kind))
                    py.append(_minutes(moment))
                    ptext.append(message)
                continue
            for day, segment_start, segment_end in _split_by_day(start, end):
                if not first_day <= day <= last_day:
                    continue
                start_minute = _minutes(segment_start)
                end_minute = 1440 if segment_end.date() > day else _minutes(segment_end)
                if end_minute == start_minute:
                    continue
                base, finish = sorted((start_minute, end_minute))
                xs.append(lane_date(day, kind))
                bases.append(base)
                heights.append(finish - base)
                text.append(f"{day:%b %d, %Y}<br>{message}")
        for activity, moment, message in points:
            moment = timezone.localtime(moment)
            if activity == kind and first_day <= moment.date() <= last_day:
                px.append(lane_date(moment.date(), kind))
                py.append(_minutes(moment))
                ptext.append(message)
        color = COLORS[kind] if kind in COLORS else MARKERS[kind][0]
        if xs:
            traces.append(
                go.Bar(
                    name=str(labels[kind]),
                    legendgroup=kind,
                    x=xs,
                    y=heights,
                    base=bases,
                    width=lane_width * 0.8,
                    marker={"color": color, "line": utils.BAR_OUTLINE},
                    hovertext=text,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
        if px:
            traces.append(
                go.Scatter(
                    name=str(labels[kind]),
                    legendgroup=kind,
                    showlegend=not xs,
                    x=px,
                    y=py,
                    mode="markers",
                    marker={
                        "color": color,
                        "size": 12,
                        "symbol": MARKERS.get(kind, (None, "circle"))[1],
                        "line": utils.BAR_OUTLINE,
                    },
                    hovertext=ptext,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
    layout = day_layout(days, _("Date"), use_24_hour=use_24_hour)
    return wrap_day_chart(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        ),
        days,
        _("Daily activity comparison"),
        minimum=480,
        day_width=210,
    )


def block_label(name, start, end, use_24_hour=False):
    """Hover text for a block: name, start-end and duration."""
    start = timezone.localtime(start)
    end = timezone.localtime(end)
    if start == end:
        return f"{name}: {clock(start, use_24_hour)} ({_("Duration not recorded")})"
    return "{}: {} - {} ({})".format(
        name,
        clock(start, use_24_hour),
        clock(end, use_24_hour),
        duration_string(end - start),
    )
