# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.db.models.manager import BaseManager

import plotly.offline as plotly
import plotly.graph_objs as go

from reports import utils


def weight_change(
    actual_weights: BaseManager, percentile_weights: BaseManager, birthday: datetime
):
    """
    Create a graph showing weight over time.
    :param actual_weights: a QuerySet of Weight instances.
    :param percentile_weights: a QuerySet of Weight Percentile instances.
    :param birthday: a datetime of the child's birthday
    :returns: a tuple of the graph's html and javascript.
    """
    measurements = list(actual_weights.order_by("-date").values_list("date", "weight"))
    weighing_dates = [row[0] for row in measurements]
    measured_weights = [row[1] for row in measurements]
    percentile_weights = (
        list(percentile_weights.order_by("age_in_days"))
        if percentile_weights is not None
        else []
    )

    actual_weights_trace = go.Scatter(
        name=_("Weight"),
        x=weighing_dates,
        y=measured_weights,
        fill="tozeroy",
        mode="lines+markers",
    )

    if percentile_weights:
        dates = [birthday + row.age_in_days for row in percentile_weights]

        # reduce percentile data xrange to end 1 day after last weigh in for formatting purposes
        # https://github.com/babybuddy/babybuddy/pull/708#discussion_r1332335789
        last_date_for_percentiles = min(max(dates), max(weighing_dates))
        end_index = dates.index(last_date_for_percentiles) + 1
        dates = dates[:end_index]

        percentile_weight_3_trace = go.Scatter(
            name=_("P3"),
            x=dates,
            y=[row.p3_weight for row in percentile_weights][:end_index],
            line={"color": "red"},
        )
        percentile_weight_15_trace = go.Scatter(
            name=_("P15"),
            x=dates,
            y=[row.p15_weight for row in percentile_weights][:end_index],
            line={"color": "orange"},
        )
        percentile_weight_50_trace = go.Scatter(
            name=_("P50"),
            x=dates,
            y=[row.p50_weight for row in percentile_weights][:end_index],
            line={"color": "green"},
        )
        percentile_weight_85_trace = go.Scatter(
            name=_("P85"),
            x=dates,
            y=[row.p85_weight for row in percentile_weights][:end_index],
            line={"color": "orange"},
        )
        percentile_weight_97_trace = go.Scatter(
            name=_("P97"),
            x=dates,
            y=[row.p97_weight for row in percentile_weights][:end_index],
            line={"color": "red"},
        )

    data = [
        actual_weights_trace,
    ]
    layout_args = utils.default_graph_layout_options()
    layout_args["barmode"] = "stack"
    layout_args["title"] = "<b>" + _("Weight") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Weight (kg)")
    if percentile_weights:
        # zoom in on the relevant dates
        layout_args["xaxis"]["range"] = [
            birthday,
            max(weighing_dates) + timedelta(days=1),
        ]
        layout_args["yaxis"]["range"] = [0, max(measured_weights) * 1.5]
        data.extend(
            [
                percentile_weight_97_trace,
                percentile_weight_85_trace,
                percentile_weight_50_trace,
                percentile_weight_15_trace,
                percentile_weight_3_trace,
            ]
        )

    fig = go.Figure({"data": data, "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)
