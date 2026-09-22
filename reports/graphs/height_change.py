# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.db.models.manager import BaseManager

import plotly.offline as plotly
import plotly.graph_objs as go

from reports import utils


def height_change(
    actual_heights: BaseManager, percentile_heights: BaseManager, birthday: datetime
):
    """
    Create a graph showing height over time.
    :param actual_heights: a QuerySet of Height instances.
    :param percentile_heights: a QuerySet of Height Percentile instances.
    :param birthday: a datetime of the child's birthday
    :returns: a tuple of the graph's html and javascript.
    """
    measurements = list(actual_heights.order_by("-date").values_list("date", "height"))
    measuring_dates = [row[0] for row in measurements]
    measured_heights = [row[1] for row in measurements]
    percentile_heights = (
        list(percentile_heights.order_by("age_in_days"))
        if percentile_heights is not None
        else []
    )

    actual_heights_trace = go.Scatter(
        name=_("Height"),
        x=measuring_dates,
        y=measured_heights,
        mode="lines+markers",
    )

    if percentile_heights:
        dates = [birthday + row.age_in_days for row in percentile_heights]

        # reduce percentile data xrange to end 1 day after last height measurement in for formatting purposes
        # https://github.com/babybuddy/babybuddy/pull/708#discussion_r1332335789
        last_date_for_percentiles = min(max(dates), max(measuring_dates))
        end_index = dates.index(last_date_for_percentiles) + 1
        dates = dates[:end_index]

        percentile_height_3_trace = go.Scatter(
            name=_("P3"),
            x=dates,
            y=[row.p3_height for row in percentile_heights][:end_index],
            line={"color": "red"},
        )
        percentile_height_15_trace = go.Scatter(
            name=_("P15"),
            x=dates,
            y=[row.p15_height for row in percentile_heights][:end_index],
            line={"color": "orange"},
        )
        percentile_height_50_trace = go.Scatter(
            name=_("P50"),
            x=dates,
            y=[row.p50_height for row in percentile_heights][:end_index],
            line={"color": "green"},
        )
        percentile_height_85_trace = go.Scatter(
            name=_("P85"),
            x=dates,
            y=[row.p85_height for row in percentile_heights][:end_index],
            line={"color": "orange"},
        )
        percentile_height_97_trace = go.Scatter(
            name=_("P97"),
            x=dates,
            y=[row.p97_height for row in percentile_heights][:end_index],
            line={"color": "red"},
        )

    data = [
        actual_heights_trace,
    ]
    layout_args = utils.default_graph_layout_options()
    layout_args["barmode"] = "stack"
    layout_args["title"] = "<b>" + _("Height") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Height (cm)")
    if percentile_heights:
        # zoom in on the relevant dates
        layout_args["xaxis"]["range"] = [
            birthday,
            max(measuring_dates) + timedelta(days=1),
        ]
        layout_args["yaxis"]["range"] = [0, max(measured_heights) * 1.5]
        data.extend(
            [
                percentile_height_97_trace,
                percentile_height_85_trace,
                percentile_height_50_trace,
                percentile_height_15_trace,
                percentile_height_3_trace,
            ]
        )

    fig = go.Figure({"data": data, "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)
