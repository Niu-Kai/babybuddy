"""Actual diaper changes per local calendar day."""

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from reports import utils


def diaperchange_amounts(instances):
    totals = list(
        instances.annotate(day=TruncDate("time"))
        .values("day")
        .annotate(total=Count("pk"))
        .order_by("day")
    )
    trace = go.Bar(
        name=_("Diaper changes"),
        x=[row["day"] for row in totals],
        y=[row["total"] for row in totals],
        hovertemplate="%{x|%b %d, %Y}<br>%{y:.0f} diapers<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout["xaxis"].update(title=_("Date"), type="date")
    layout["yaxis"].update(
        title=_("Diaper changes"),
        **utils.count_axis(max((row["total"] for row in totals), default=0))
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
