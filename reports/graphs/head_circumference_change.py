# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.db.models.manager import BaseManager

import plotly.offline as plotly
import plotly.graph_objs as go

from reports import utils


def head_circumference_change(
    objects: BaseManager,
    percentiles: BaseManager = None,
    birthday: datetime = None,
):
    """
    Create a graph showing head circumference over time, optionally against
    the WHO head-circumference-for-age percentiles.
    :param objects: a QuerySet of Head Circumference instances.
    :param percentiles: a QuerySet of HeadCircumferencePercentile instances.
    :param birthday: a date of the child's birthday (needed with percentiles).
    :returns: a tuple of the graph's html and javascript.
    """
    objects = objects.order_by("-date")

    measure_dates = list(objects.values_list("date", flat=True))
    measures = list(objects.values_list("head_circumference", flat=True))

    trace = go.Scatter(
        name=_("Head Circumference"),
        x=measure_dates,
        y=measures,
        fill="tozeroy",
        mode="lines+markers",
    )
    data = [trace]

    layout_args = utils.default_graph_layout_options()
    layout_args["barmode"] = "stack"
    layout_args["title"] = "<b>" + _("Head Circumference") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Head Circumference")

    if percentiles and birthday:
        percentiles = percentiles.order_by("age_in_days")
        dates = [
            birthday + age for age in percentiles.values_list("age_in_days", flat=True)
        ]
        # Stop the percentile curves one day after the last measurement.
        last_date = min(max(dates), max(measure_dates))
        end_index = dates.index(last_date) + 1
        dates = dates[:end_index]

        curves = (
            ("p97_head_circumference", _("P97"), "red"),
            ("p85_head_circumference", _("P85"), "orange"),
            ("p50_head_circumference", _("P50"), "green"),
            ("p15_head_circumference", _("P15"), "orange"),
            ("p3_head_circumference", _("P3"), "red"),
        )
        for field, name, color in curves:
            data.append(
                go.Scatter(
                    name=name,
                    x=dates,
                    y=list(percentiles.values_list(field, flat=True))[:end_index],
                    line={"color": color},
                )
            )
        layout_args["xaxis"]["range"] = [
            birthday,
            max(measure_dates) + timedelta(days=1),
        ]
        layout_args["yaxis"]["range"] = [0, max(measures) * 1.5]

    fig = go.Figure({"data": data, "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)
