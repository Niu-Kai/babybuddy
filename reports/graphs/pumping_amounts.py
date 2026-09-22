from collections import defaultdict
from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core.units import convert
from reports import utils


def pumping_amounts(objects, unit="mL"):
    totals = defaultdict(float)
    for entry in objects:
        totals[timezone.localtime(entry.start).date()] += entry.amount or 0
    days = sorted(totals)
    if not days:
        return None, None
    amounts = [round(convert(totals[day], "mL", unit), 2) for day in days]
    trace = go.Bar(
        name=_("Pumped milk"),
        x=days,
        y=amounts,
        hovertemplate="%{x|%b %d, %Y}<br>%{y:.2f} " + unit + "<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout["xaxis"].update(
        title=_("Date"),
        type="date",
        autorange=True,
        autorangeoptions=utils.autorangeoptions(days),
    )
    layout["yaxis"].update(
        title=_("Pumping amount") + " (" + unit + ")", rangemode="tozero"
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
