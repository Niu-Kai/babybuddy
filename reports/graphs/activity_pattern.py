# -*- coding: utf-8 -*-
"""
A day-by-day chart of every activity: one column per day, blocks for sleep,
feedings, tummy time and pumping, markers for diaper changes and medication
(babybuddy/babybuddy#218, #881).
"""

from collections import OrderedDict
from datetime import timedelta

from django.utils import formats, timezone
from django.utils.translation import gettext as _

import plotly.graph_objs as go
import plotly.offline as plotly

from core.utils import duration_string
from reports import utils

GAP = "rgba(0, 0, 0, 0)"
COLORS = {
    "sleep": "rgb(35, 110, 150)",
    "feeding": "rgb(79, 184, 240)",
    "tummytime": "rgb(62, 207, 131)",
    "pumping": "rgb(192, 132, 252)",
}
MARKERS = {
    "diaperchange": ("rgb(240, 100, 122)", "diamond"),
    "medication": ("rgb(255, 168, 56)", "star"),
}
MINUTES_PER_DAY = 24 * 60


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


def activity_pattern(intervals, points, first_day, last_day, labels):
    """
    Create the graph.
    :param intervals: a list of (kind, start, end, label) tuples.
    :param points: a list of (kind, time, label) tuples.
    :param first_day: date of the first column.
    :param last_day: date of the last column.
    :param labels: a dict of kind -> legend label.
    :returns: a tuple of the graph's html and javascript.
    """
    period = (last_day - first_day).days + 1
    days = OrderedDict(
        ((first_day + timedelta(days=d)).isoformat(), []) for d in range(period)
    )

    # Collect each day's blocks, then lay them out without overlaps.
    pieces = {key: [] for key in days}
    for kind, start, end, label in intervals:
        for day, piece_start, piece_end in _split_by_day(start, end):
            key = day.isoformat()
            if key in pieces:
                pieces[key].append(
                    (_minutes(piece_start), _minutes(piece_end), kind, label)
                )
    if any(pieces.values()):
        for key, blocks in pieces.items():
            cursor = 0.0
            for start_minute, end_minute, kind, label in sorted(blocks):
                start_minute = max(start_minute, cursor)
                end_minute = max(end_minute, start_minute)
                if start_minute > cursor:
                    days[key].append((start_minute - cursor, GAP, None))
                days[key].append((end_minute - start_minute, COLORS[kind], label))
                cursor = end_minute
            days[key].append((MINUTES_PER_DAY - cursor, GAP, None))

    # Dates at 12:00 so each bar covers its whole day on a date axis.
    dates = ["{} 12:00:00".format(key) for key in days]

    traces = []
    max_i = max((len(blocks) for blocks in days.values()), default=0)
    for i in range(max_i):
        y, colors, text = [], [], []
        for blocks in days.values():
            if i < len(blocks):
                minutes, color, label = blocks[i]
                y.append(minutes)
                colors.append(color)
                text.append(label)
            else:
                y.append(None)
                colors.append(GAP)
                text.append(None)
        traces.append(
            go.Bar(
                x=dates,
                y=y,
                hovertext=text,
                hoverinfo="text",
                marker={"color": colors},
                showlegend=False,
            )
        )

    for kind, (color, symbol) in MARKERS.items():
        xs, ys, text = [], [], []
        for point_kind, moment, label in points:
            if point_kind != kind:
                continue
            moment = timezone.localtime(moment)
            key = moment.date().isoformat()
            if key in days:
                xs.append("{} 12:00:00".format(key))
                ys.append(_minutes(moment))
                text.append(label)
        if xs:
            traces.append(
                go.Scatter(
                    name=labels[kind],
                    x=xs,
                    y=ys,
                    mode="markers",
                    marker={"color": color, "symbol": symbol, "size": 9},
                    hovertext=text,
                    hoverinfo="text",
                )
            )

    # Legend entries for the block colours.
    for kind, color in COLORS.items():
        if kind in labels:
            traces.append(
                go.Bar(name=labels[kind], x=[dates[0]], y=[0], marker={"color": color})
            )

    layout_args = utils.default_graph_layout_options()
    layout_args["margin"]["b"] = 100
    layout_args["barmode"] = "stack"
    layout_args["bargap"] = 0
    layout_args["hovermode"] = "closest"
    layout_args["title"] = "<b>" + _("Daily Activity") + "</b>"
    layout_args["height"] = 800
    layout_args["legend"] = {"orientation": "h", "y": -0.15}
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["tickangle"] = -65
    layout_args["xaxis"]["tickformat"] = "%b %e\n%Y"
    layout_args["xaxis"]["ticklabelmode"] = "period"

    start = timezone.localtime().strptime("12:00 AM", "%I:%M %p")
    ticks = OrderedDict()
    for i in range(0, MINUTES_PER_DAY, 60):
        ticks[i] = formats.time_format(start + timedelta(minutes=i), "TIME_FORMAT")
    layout_args["yaxis"]["title"] = _("Time of day")
    layout_args["yaxis"]["range"] = [MINUTES_PER_DAY, 0]
    layout_args["yaxis"]["tickmode"] = "array"
    layout_args["yaxis"]["tickvals"] = list(ticks.keys())
    layout_args["yaxis"]["ticktext"] = list(ticks.values())
    layout_args["yaxis"]["tickfont"] = {"size": 10}

    fig = go.Figure({"data": traces, "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)


def block_label(name, start, end):
    """Hover text for a block: name, start-end and duration."""
    start = timezone.localtime(start)
    end = timezone.localtime(end)
    return "{}: {} - {} ({})".format(
        name,
        formats.time_format(start, "TIME_FORMAT"),
        formats.time_format(end, "TIME_FORMAT"),
        duration_string(end - start),
    )
