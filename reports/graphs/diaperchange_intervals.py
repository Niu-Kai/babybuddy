"""Elapsed time since the preceding diaper change, regardless of type."""

from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core.utils import duration_string
from reports import utils


def diaperchange_intervals(changes):
    changes = list(changes.order_by("time", "pk"))
    times, hours, details = [], [], []
    for previous, current in zip(changes, changes[1:]):
        duration = current.time - previous.time
        if duration.total_seconds() <= 0:
            continue
        kind = (
            _("Wet + solid")
            if current.wet and current.solid
            else (
                _("Wet") if current.wet else _("Solid") if current.solid else _("Other")
            )
        )
        times.append(timezone.localtime(current.time))
        hours.append(duration.total_seconds() / 3600)
        details.append(str(kind) + "<br>" + duration_string(duration))
    if not times:
        return None, None
    trace = go.Scatter(
        name=_("Time between changes"),
        x=times,
        y=hours,
        customdata=details,
        mode="lines+markers",
        line={"width": 2, "shape": "linear"},
        marker={"size": 6},
        hovertemplate="%{x|%b %d, %Y %H:%M}<br>%{customdata}<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout.update(showlegend=False)
    layout["xaxis"].update(title=_("Date"), type="date")
    layout["yaxis"].update(
        title=_("Time since previous change (hours)"), rangemode="tozero"
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
