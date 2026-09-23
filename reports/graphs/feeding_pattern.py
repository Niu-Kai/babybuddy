"""Feeding sessions compared by local day, without stacking time gaps."""

from collections import Counter, defaultdict
from datetime import timedelta, timezone as utc_timezone
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
import plotly.graph_objects as go
import plotly.offline as plotly
from core.models import Feeding
from core.utils import duration_string
from reports import utils
from reports.graphs.activity_pattern import _split_by_day, _minutes
from reports.graphs.day_grid import clock, day_layout, wrap_day_chart


def feeding_pattern(
    feedings, first_day=None, last_day=None, use_24_hour=False, session_methods=None
):
    feedings = sorted(feedings, key=lambda entry: entry.start)
    if not feedings:
        return None, None
    first_day = first_day or timezone.localtime(feedings[0].start).date()
    last_day = last_day or max(
        timezone.localtime(item.end or item.start).date() for item in feedings
    )
    days = [
        first_day + timedelta(days=index)
        for index in range((last_day - first_day).days + 1)
    ]
    if not days:
        return None, None
    methods = [
        (method, label)
        for method, label in (session_methods or Feeding.method.field.choices)
        if any(item.method == method for item in feedings)
    ]
    if any(not item.method for item in feedings):
        methods.append(("", _("Unspecified")))
    method_colors = {
        method: utils.CHART_COLORS[index % len(utils.CHART_COLORS)]
        for index, (method, _) in enumerate(
            session_methods or Feeding.method.field.choices
        )
    }
    counts = Counter(timezone.localtime(item.start).date() for item in feedings)
    summaries = [
        (
            ngettext("%(count)s session", "%(count)s sessions", counts[day])
            if session_methods
            else ngettext("%(count)s feeding", "%(count)s feedings", counts[day])
        )
        % {"count": counts[day]}
        for day in days
    ]
    # Only share a day column when sessions actually overlap. Different methods
    # at different times can use the full width instead of tiny permanent lanes.
    segments = defaultdict(list)
    for entry in feedings:
        for day, start, end in _split_by_day(entry.start, entry.end or entry.start):
            if first_day <= day <= last_day:
                base, finish = sorted(
                    (_minutes(start), 1440 if end.date() > day else _minutes(end))
                )
                segments[day].append((base, max(finish, base + 0.5), entry.pk))
    positions = {}
    for day, entries in segments.items():
        clusters = []
        finish = -1
        for item in sorted(entries):
            if item[0] >= finish:
                clusters.append([])
            clusters[-1].append(item)
            finish = max(finish, item[1])
        for cluster in clusters:
            lanes, assigned = [], []
            for start, end, key in cluster:
                lane = next(
                    (i for i, stop in enumerate(lanes) if stop <= start), len(lanes)
                )
                if lane == len(lanes):
                    lanes.append(end)
                else:
                    lanes[lane] = end
                assigned.append((key, lane))
            width = 0.72 / len(lanes)
            for key, lane in assigned:
                positions[key, day] = ((lane - (len(lanes) - 1) / 2) * width, width)
    traces = []
    annotations = []
    for index, (method, label) in enumerate(methods):
        xs, bases, lengths, text, widths = [], [], [], [], []
        px, py, ptext = [], [], []
        for entry in feedings:
            if (entry.method or "") != method:
                continue
            start = timezone.localtime(entry.start)
            end = timezone.localtime(entry.end or entry.start)
            if end == start:
                if first_day <= start.date() <= last_day:
                    offset, _width = positions[entry.pk, start.date()]
                    px.append((start.date() - first_day).days + offset)
                    py.append(_minutes(start))
                    ptext.append(
                        f"{start:%b %d, %Y}<br>{label}: {clock(start, use_24_hour)}<br>{_("Duration not recorded")}"
                    )
                continue
            for day, start, end in _split_by_day(entry.start, entry.end):
                duration = end.astimezone(utc_timezone.utc) - start.astimezone(
                    utc_timezone.utc
                )
                if not first_day <= day <= last_day or duration.total_seconds() <= 0:
                    continue
                base, finish = sorted(
                    (_minutes(start), 1440 if end.date() > day else _minutes(end))
                )
                offset, width = positions[entry.pk, day]
                xs.append((day - first_day).days + offset)
                widths.append(width * 0.92)
                if width > 0.5:
                    minutes = round(duration.total_seconds() / 60)
                    annotations.append(
                        dict(
                            x=(day - first_day).days,
                            y=base,
                            yshift=14 if session_methods else 12,
                            text=f"{clock(start, use_24_hour)} · {minutes}m",
                            showarrow=False,
                            font=dict(size=15 if session_methods else 13),
                        )
                    )
                bases.append(base)
                lengths.append(max(finish - base, 0.5))
                text.append(
                    f"{day:%b %d, %Y}<br>{label}: {clock(start, use_24_hour)} - {clock(end, use_24_hour)}<br>{duration_string(duration)}"
                )
        color = method_colors.get(method, "#a3afbd")
        if xs:
            traces.append(
                go.Bar(
                    name=str(label),
                    legendgroup=method,
                    x=xs,
                    y=lengths,
                    base=bases,
                    width=widths,
                    marker=dict(color=color, line=utils.BAR_OUTLINE),
                    hovertext=text,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
        if px:
            traces.append(
                go.Scatter(
                    name=str(label),
                    legendgroup=method,
                    showlegend=not xs,
                    x=px,
                    y=py,
                    mode="markers",
                    marker=dict(color=color, size=12, line=utils.BAR_OUTLINE),
                    hovertext=ptext,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
    layout = day_layout(
        days,
        (
            _("Sessions started per day")
            if session_methods
            else _("Feedings started per day")
        ),
        summaries,
        use_24_hour,
    )
    if session_methods:
        # Leave enough vertical space for short sessions and readable labels.
        # Wider day columns are paged by the shared responsive chart controls.
        layout.update(height=1120)
        layout["margin"].update(l=100, r=32, b=190)
        layout["legend"].update(y=-0.13, font=dict(size=15), tracegroupgap=12)
        ticks = list(range(0, 1441, 60))
        origin = timezone.localtime(feedings[0].start).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        layout["yaxis"].update(
            tickvals=ticks,
            ticktext=[
                clock(origin + timedelta(minutes=value), use_24_hour) for value in ticks
            ],
        )
        readable = []
        previous_y = {}
        for annotation in sorted(annotations, key=lambda item: (item["x"], item["y"])):
            day = first_day + timedelta(days=int(annotation["x"]))
            # Do not put a label over an earlier session, including sessions
            # whose own labels were hidden because they overlap.
            clear_above = all(
                end <= annotation["y"] - 45
                for start, end, _key in segments[day]
                if start < annotation["y"]
            )
            if (
                clear_above
                and annotation["y"] - previous_y.get(annotation["x"], -100) >= 45
            ):
                readable.append(annotation)
                previous_y[annotation["x"]] = annotation["y"]
        annotations = readable
    layout["annotations"] = annotations
    return wrap_day_chart(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        ),
        days,
        (
            _("Daily pumping and nursing comparison")
            if session_methods
            else _("Daily feeding comparison")
        ),
        minimum=640 if session_methods else 480,
        day_width=360 if session_methods else 180,
    )
