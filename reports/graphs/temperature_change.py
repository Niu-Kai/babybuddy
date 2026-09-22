from django.utils import timezone
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core.units import convert
from reports import utils


def temperature_change(objects, unit="C"):
    points = list(objects.order_by("time", "pk").values_list("time", "temperature"))
    trace = go.Scatter(
        name=_("Temperature"),
        x=[timezone.localtime(moment).isoformat() for moment, value in points],
        y=[round(convert(value, "C", unit), 2) for moment, value in points],
        mode="lines+markers",
        line={"width": 3, "shape": "linear"},
        marker={"size": 7},
        hovertemplate="%{x|%b %d, %Y %H:%M}<br>%{y:.1f} °" + unit + "<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout["xaxis"].update(title=_("Time"), type="date")
    layout["yaxis"].update(
        title=_("Temperature") + " (°" + unit + ")",
        rangemode="normal",
        tickformat=".1f",
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
