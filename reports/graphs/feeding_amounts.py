from collections import defaultdict
from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core import models
from core.units import convert
from reports import utils


def feeding_amounts(instances, unit="mL"):
    totals = defaultdict(lambda: defaultdict(float))
    for entry in instances:
        day = timezone.localtime(entry.start).date()
        for kind, amount in (
            (entry.type, entry.amount),
            (entry.secondary_type, entry.secondary_amount),
        ):
            if kind and kind != "solid food" and amount is not None:
                totals[day][kind] += amount
    days = sorted(totals)
    traces = []
    for kind, label in models.Feeding._meta.get_field("type").choices:
        values = [round(convert(totals[day][kind], "mL", unit), 2) for day in days]
        if any(values):
            traces.append(
                go.Bar(
                    name=str(label),
                    x=days,
                    y=values,
                    hovertemplate="%{x|%b %d, %Y}<br>%{y:.2f} "
                    + unit
                    + "<extra>%{fullData.name}</extra>",
                )
            )
    if not traces:
        return None, None
    layout = utils.default_graph_layout_options()
    layout.update(barmode="stack")
    layout["xaxis"].update(title=_("Date"), type="date")
    layout["yaxis"].update(
        title=_("Feeding amount") + " (" + unit + ")", rangemode="tozero"
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
