# -*- coding: utf-8 -*-
from django.utils.translation import gettext as _

import plotly.offline as plotly
import plotly.graph_objs as go

from core.utils import duration_parts

from reports import utils


def feeding_intervals(instances):
    """
    Create a graph showing intervals of feeding instances over time.

    :param instances: a QuerySet of Feeding instances.
    :returns: a tuple of the graph's html and javascript.
    """
    moments = instances.order_by("start").values_list("start", flat=True).iterator()
    intervals, times = [], []
    previous = next(moments, None)
    for moment in moments:
        interval = moment - previous
        if interval.total_seconds() > 0:
            intervals.append(interval)
            times.append(moment)
        previous = moment

    if not intervals:
        return None, None

    trace_avg = go.Scatter(
        name=_("Interval"),
        line=dict(shape="spline"),
        x=times,
        y=[i.total_seconds() / 3600 for i in intervals],
        hoverinfo="text",
        text=[_duration_string_hms(i) for i in intervals],
    )

    layout_args = utils.default_graph_layout_options()
    layout_args["title"] = "<b>" + _("Feeding intervals") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["type"] = "date"
    layout_args["xaxis"]["autorange"] = True
    layout_args["xaxis"]["autorangeoptions"] = utils.autorangeoptions(trace_avg.x)
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Feeding interval (hours)")

    fig = go.Figure({"data": [trace_avg], "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)


def _duration_string_hms(duration):
    """
    Format a duration string with hours, minutes and seconds. This is
    intended to fit better in smaller spaces on a graph.
    :returns: a string of the form Xm.
    """
    h, m, s = duration_parts(duration)
    return "{}h{}m{}s".format(h, m, s)
