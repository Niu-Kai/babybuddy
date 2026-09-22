from datetime import timedelta
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from reports import utils


def feeding_duration(instances):
    totals = list(
        instances.filter(duration__gt=timedelta(0))
        .annotate(day=TruncDate("start"))
        .values("day")
        .annotate(average=Avg("duration"), count=Count("pk"))
        .order_by("day")
    )
    if not totals:
        return None, None
    trace = go.Scatter(
        name=_("Average feeding duration"),
        x=[row["day"] for row in totals],
        y=[round(row["average"].total_seconds() / 60, 2) for row in totals],
        customdata=[row["count"] for row in totals],
        mode="lines+markers",
        line={"shape": "linear", "width": 2},
        hovertemplate="%{x|%b %d, %Y}<br>%{y:.1f} min<br>%{customdata} timed feedings<extra></extra>",
    )
    layout = utils.default_graph_layout_options()
    layout["xaxis"].update(title=_("Date"), type="date")
    layout["yaxis"].update(title=_("Average duration (minutes)"), rangemode="tozero")
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=[trace], layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
