from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from reports import utils


def diaperchange_types(changes):
    totals = list(
        changes.annotate(day=TruncDate("time"))
        .values("day")
        .annotate(
            wet_only=Count("pk", filter=Q(wet=True, solid=False)),
            solid_only=Count("pk", filter=Q(wet=False, solid=True)),
            both=Count("pk", filter=Q(wet=True, solid=True)),
            other=Count("pk", filter=Q(wet=False, solid=False)),
        )
        .order_by("day")
    )
    traces = [
        go.Bar(
            name=str(label),
            x=[row["day"] for row in totals],
            y=[row[key] for row in totals],
            hovertemplate="%{x|%b %d, %Y}<br>%{y:.0f} diapers<extra>%{fullData.name}</extra>",
        )
        for key, label in (
            ("wet_only", _("Wet only")),
            ("solid_only", _("Solid only")),
            ("both", _("Wet + solid")),
            ("other", _("Other")),
        )
        if any(row[key] for row in totals)
    ]
    layout = utils.default_graph_layout_options()
    layout.update(barmode="stack")
    layout["xaxis"].update(title=_("Date"), type="date")
    layout["yaxis"].update(
        title=_("Diaper changes"),
        **utils.count_axis(
            max(
                (
                    sum(row[key] for key in ("wet_only", "solid_only", "both", "other"))
                    for row in totals
                ),
                default=0,
            )
        )
    )
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
