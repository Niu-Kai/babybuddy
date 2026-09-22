"""Recorded sleep on a local-time day grid; gaps are not inferred awake time."""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as utc_timezone

from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly

from core.utils import duration_string
from reports import utils
from reports.graphs.activity_pattern import _split_by_day

ASLEEP_COLOR = "#6487a7"
NAP_COLOR = "#8f80a7"


def sleep_pattern(sleeps, first_day=None, last_day=None, use_24_hour=False):
    sleeps = list(sleeps.order_by("start"))
    if not sleeps:
        return None, None
    first_day = first_day or timezone.localtime(sleeps[0].start).date()
    last_day = last_day or max(timezone.localtime(entry.end).date() for entry in sleeps)
    days = [
        first_day + timedelta(days=index)
        for index in range((last_day - first_day).days + 1)
    ]
    if not days:
        return None, None
    dates = [day.isoformat() for day in days]
    width = 0.72 if len(days) > 1 else 0.35
    recorded = defaultdict(list)
    traces = [
        go.Bar(
            name=_("No sleep recorded"),
            x=dates,
            y=[1440] * len(days),
            base=0,
            width=width,
            marker={
                "color": "rgba(135,151,171,0.12)",
                "line": {"color": "rgba(135,151,171,0.4)", "width": 1},
            },
            hoverinfo="skip",
        )
    ]

    def clock(moment):
        return (
            moment.strftime("%H:%M" if use_24_hour else "%I:%M %p").lstrip("0")
            if not use_24_hour
            else moment.strftime("%H:%M")
        )

    for nap, name, color in (
        (False, _("Sleep"), ASLEEP_COLOR),
        (True, _("Nap"), NAP_COLOR),
    ):
        xs, bases, lengths, labels = [], [], [], []
        for entry in sleeps:
            if entry.nap != nap:
                continue
            for day, start, end in _split_by_day(entry.start, entry.end):
                if not first_day <= day <= last_day:
                    continue
                if end.astimezone(utc_timezone.utc) <= start.astimezone(
                    utc_timezone.utc
                ):
                    continue
                start_minute = start.hour * 60 + start.minute + start.second / 60
                end_minute = (
                    1440
                    if end.date() > day
                    else end.hour * 60 + end.minute + end.second / 60
                )
                duration = end.astimezone(utc_timezone.utc) - start.astimezone(
                    utc_timezone.utc
                )
                # A repeated clock hour can end before it starts on the wall-time
                # axis. Display its covered clock span; hover retains real duration.
                base, finish = sorted((start_minute, end_minute))
                xs.append(day.isoformat())
                recorded[day].append(
                    (
                        start.astimezone(utc_timezone.utc),
                        end.astimezone(utc_timezone.utc),
                    )
                )
                bases.append(base)
                lengths.append(max(finish - base, 0.5))
                labels.append(
                    f"{day:%b %d, %Y}<br>{name}: {clock(start)} - {clock(end)}<br>{duration_string(duration)}"
                )
        if xs:
            traces.append(
                go.Bar(
                    name=name,
                    x=xs,
                    y=lengths,
                    base=bases,
                    width=width,
                    marker={"color": color, "line": {"color": "#a3afbd", "width": 1.5}},
                    hovertext=labels,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
    # Merge overlapping entries so daily totals count actual recorded time once.
    daily_labels = []
    for day in days:
        merged = []
        for start, end in sorted(recorded[day]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        minutes = round(
            sum((end - start).total_seconds() for start, end in merged) / 60
        )
        total = _("No entries")
        if merged:
            hours, remainder = divmod(minutes, 60)
            total = f"{hours}h {remainder:02d}m"
        daily_labels.append(f"{day:%a}<br>{day:%b %d}<br><b>{total}</b>")
    layout = utils.default_graph_layout_options()
    layout["margin"]["b"] = 150
    layout["legend"].update(y=-0.25)
    layout.update(height=640, barmode="overlay", bargap=0.2, hovermode="closest")
    layout["xaxis"].update(
        title=_("Recorded sleep per day"),
        type="category",
        categoryorder="array",
        categoryarray=dates,
        tickmode="array",
        tickvals=dates,
        ticktext=daily_labels,
        tickangle=0,
        range=[-0.5, len(days) - 0.5],
        fixedrange=True,
    )
    ticks = list(range(0, 1441, 180))
    origin = datetime.combine(first_day, time())
    labels = [clock(origin + timedelta(minutes=minute)) for minute in ticks]
    layout["yaxis"].update(
        title=_("Time of day"),
        range=[1440, 0],
        tickmode="array",
        tickvals=ticks,
        ticktext=labels,
        showgrid=True,
    )
    html, js = utils.split_graph_output(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )

    # Keep day columns readable in longer periods, and a lone day compact.
    chart_width = max(360, len(days) * 82 + 120)
    html = (
        f'<div class="sleep-comparison-scroll" style="max-width:{chart_width}px" '
        f'tabindex="0" role="region" aria-label="{_("Daily sleep comparison")}">'
        f'<div style="min-width:{chart_width}px">{html}</div></div>'
    )
    return html, js
