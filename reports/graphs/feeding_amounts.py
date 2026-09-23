"""Daily quantities grouped by milk type or individual feeding session."""

from collections import defaultdict
from datetime import datetime, time
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext as _
import plotly.graph_objects as go
import plotly.offline as plotly
from core import models
from core.units import convert
from core.top_ups import amount_parts
from reports import utils


def feeding_amounts(
    instances, unit="mL", group="type", first_day=None, last_day=None, use_24_hour=False
):
    totals = defaultdict(lambda: defaultdict(float))
    sessions = defaultdict(list)
    labels = dict(models.Feeding._meta.get_field("type").choices)
    for entry in sorted(instances, key=lambda item: (item.start, item.pk or 0)):
        daily = defaultdict(list)
        for at, kind, amount in amount_parts(entry):
            local = timezone.localtime(at)
            day = local.date()
            if (first_day and day < first_day) or (last_day and day > last_day):
                continue
            value = convert(amount, "mL", unit)
            totals[day][kind] += value
            stamp = local.strftime("%H:%M" if use_24_hour else "%I:%M %p").lstrip("0")
            if use_24_hour:
                stamp = local.strftime("%H:%M")
            prefix = str(_("Top-up bottle")) + " · " if at == entry.top_up_at else ""
            daily[day].append(
                (
                    value,
                    f"{escape(prefix + stamp)} · {escape(labels.get(kind, kind))}: {value:.2f} {escape(unit)}",
                )
            )
        for day, parts in daily.items():
            sessions[day].append(
                (sum(p[0] for p in parts), "<br>".join(p[1] for p in parts))
            )
    days = sorted(totals)
    # Center each daily bar inside its day. Plotly otherwise gives a single
    # date point a millisecond-wide bar, invisible with a full-day filter.
    positions = [datetime.combine(day, time(12)) for day in days]
    day_width = round(0.7 * 24 * 60 * 60 * 1000)
    traces = []
    if group == "session":
        for index in range(max((len(value) for value in sessions.values()), default=0)):
            values = [
                sessions[day][index][0] if index < len(sessions[day]) else None
                for day in days
            ]
            details = [
                sessions[day][index][1] if index < len(sessions[day]) else ""
                for day in days
            ]
            traces.append(
                go.Bar(
                    name=_("Feeding %(number)s") % {"number": index + 1},
                    x=positions,
                    width=day_width,
                    y=values,
                    customdata=details,
                    marker={
                        "color": utils.CHART_COLORS[index % len(utils.CHART_COLORS)],
                        "line": utils.BAR_OUTLINE,
                    },
                    hovertemplate="%{x|%b %d, %Y}<br>%{customdata}<br>"
                    + str(_("Total"))
                    + ": %{y:.2f} "
                    + unit
                    + "<extra>%{fullData.name}</extra>",
                )
            )
    else:
        for kind, label in labels.items():
            values = [round(totals[day][kind], 2) for day in days]
            if any(values):
                traces.append(
                    go.Bar(
                        name=str(label),
                        x=positions,
                        width=day_width,
                        y=values,
                        marker={"line": utils.BAR_OUTLINE},
                        hovertemplate="%{x|%b %d, %Y}<br>%{y:.2f} "
                        + unit
                        + "<extra>%{fullData.name}</extra>",
                    )
                )
    if not traces:
        return None, None
    layout = utils.default_graph_layout_options()
    layout.update(barmode="stack", bargap=0.3)
    if group == "session":
        layout.update(hovermode="closest", showlegend=False)
    layout["xaxis"].update(title=_("Date"), type="date", tickformat="%b %d", nticks=12)
    if len(days) == 1:
        layout["xaxis"].update(tickmode="array", tickvals=positions)
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
