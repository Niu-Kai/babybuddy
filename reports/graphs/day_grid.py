"""Shared presentation for reports comparing time-of-day across dates."""

from datetime import datetime, time, timedelta
from django.utils.translation import gettext as _
from django.utils.html import escape
from reports import utils


def clock(moment, use_24_hour=False):
    return (
        moment.strftime("%H:%M")
        if use_24_hour
        else moment.strftime("%I:%M %p").lstrip("0")
    )


def day_layout(days, title, summaries=None, use_24_hour=False):
    layout = utils.default_graph_layout_options()
    layout["margin"]["b"] = 150
    layout["legend"].update(y=-0.25)
    layout.update(height=820, barmode="overlay", hovermode="closest")
    layout["font"]["size"] = 16
    layout["xaxis"]["tickfont"] = {"size": 15}
    layout["yaxis"]["tickfont"] = {"size": 15}
    labels = [f"{day:%a}<br>{day:%b %d}" for day in days]
    if summaries:
        labels = [
            f"{label}<br><b>{escape(summary)}</b>"
            for label, summary in zip(labels, summaries)
        ]
    layout["xaxis"].update(
        title=title,
        type="linear",
        tickmode="array",
        tickvals=list(range(len(days))),
        ticktext=labels,
        tickangle=0,
        range=[-0.5, min(3, len(days)) - 0.5],
        fixedrange=True,
    )
    ticks = list(range(0, 1441, 180))
    origin = datetime.combine(days[0], time())
    layout["yaxis"].update(
        title=_("Time of day"),
        range=[1440, 0],
        tickmode="array",
        tickvals=ticks,
        ticktext=[
            clock(origin + timedelta(minutes=value), use_24_hour) for value in ticks
        ],
        showgrid=True,
    )
    layout["shapes"] = [
        dict(
            type="rect",
            xref="x",
            yref="paper",
            x0=index - 0.46,
            x1=index + 0.46,
            y0=0,
            y1=1,
            layer="below",
            fillcolor="rgba(135,151,171,0.06)",
            line=dict(color="rgba(135,151,171,0.28)", width=1),
        )
        for index in range(len(days))
    ]
    return layout


def wrap_day_chart(output, days, label, minimum=360, day_width=180):
    html, js = utils.split_graph_output(output)
    return (
        f'<div class="day-comparison" data-day-comparison '
        f'data-first-day="{days[0].isoformat()}" data-day-count="{len(days)}" '
        f'data-day-width="{day_width}" style="max-width:{minimum if len(days) == 1 else 100000}px;margin-inline:auto" role="region" aria-label="{escape(label)}">'
        '<div class="d-flex align-items-center justify-content-between gap-2 mb-2" data-day-controls>'
        f'<button type="button" class="btn btn-outline-primary btn-sm" data-day-previous>{_("Previous days")}</button>'
        '<span class="small" data-day-range aria-live="polite"></span>'
        f'<button type="button" class="btn btn-outline-primary btn-sm" data-day-next>{_("Next days")}</button>'
        f"</div>{html}</div>",
        js,
    )
