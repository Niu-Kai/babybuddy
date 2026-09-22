from collections import Counter
import math
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from reports import utils


def diaperchange_lifetimes(changes):
    moments = list(changes.order_by("time").values_list("time", flat=True))
    hours = [
        (second - first).total_seconds() / 3600
        for first, second in zip(moments, moments[1:])
        if second > first
    ]
    if not hours:
        return None, None
    size = max(0.5, math.ceil(max(hours) / 12 * 2) / 2)
    totals = Counter(math.floor(value / size) for value in hours)
    bins = list(range(max(totals) + 1))
    counts = [totals[index] for index in bins]
    trace = go.Bar(
        name=_("Intervals"),
        x=[(index + 0.5) * size for index in bins],
        y=counts,
        width=size * 0.86,
        customdata=[f"{index * size:g} - {(index + 1) * size:g}" for index in bins],
        hovertemplate="%{customdata} hours<br>%{y:.0f} intervals<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout.update(hovermode="closest", showlegend=False)
    layout["xaxis"].update(
        title=_("Time between changes (hours)"), type="linear", rangemode="tozero"
    )
    layout["yaxis"].update(
        title=_("Number of intervals"), **utils.count_axis(max(counts))
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
