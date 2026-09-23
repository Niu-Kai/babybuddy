"""Age-matched growth lines with WHO median references."""

import json
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import plotly.offline as plotly
from django.utils.translation import gettext as _

from core import models
from core.units import SPECS, convert
from reports import utils

PERMISSIONS = {
    "weight": "core.view_weight",
    "height": "core.view_height",
    "headcircumference": "core.view_headcircumference",
    "bmi": "core.view_bmi",
}

METRICS = {
    "weight": (models.Weight, "weight", models.WeightPercentile, _("Weight")),
    "height": (models.Height, "height", models.HeightPercentile, _("Height")),
    "headcircumference": (
        models.HeadCircumference,
        "head_circumference",
        models.HeadCircumferencePercentile,
        _("Head circumference"),
    ),
    "bmi": (models.BMI, "bmi", None, _("BMI")),
}


@lru_cache(maxsize=1)
def bmi_percentiles():
    return json.loads(
        (Path(__file__).parent / "data" / "who_bmi_percentiles.json").read_text()
    )


@lru_cache(maxsize=1)
def bmi_medians():
    return json.loads(
        (Path(__file__).parent / "data" / "who_bmi_medians.json").read_text()
    )


def growth_chart(objects, child, metric, unit, references, percentiles=False):
    model, field, percentile_model, label = METRICS[metric]
    birthday = child.corrected_birth_date
    measurements = list(objects.order_by("date", "pk").values_list("date", field))
    if not measurements:
        return None, None
    ages = [(day - birthday).days for day, value in measurements]
    scale, age_label = (
        (7, _("Age (weeks)")) if max(ages) <= 91 else (30.4375, _("Age (months)"))
    )
    if child.is_premature:
        age_label = (
            _("Corrected age (weeks)") if scale == 7 else _("Corrected age (months)")
        )
    canonical = SPECS[metric][1] if metric in SPECS else ""
    unit_label = dict(SPECS[metric][3])[unit] if metric in SPECS else "kg/m²"

    def display(value):
        return (
            round(convert(value, canonical, unit), 2) if canonical else round(value, 2)
        )

    traces = [
        go.Scatter(
            name=str(child),
            x=[age / scale for age in ages],
            y=[display(value) for day, value in measurements],
            customdata=[
                [day.isoformat(), age] for (day, value), age in zip(measurements, ages)
            ],
            mode="lines+markers",
            line={"color": "#6487a7", "width": 3, "shape": "linear"},
            marker={"size": 8},
            connectgaps=False,
            hovertemplate="%{customdata[0]}<br>%{y:.2f} "
            + unit_label
            + "<br>"
            + str(_("Corrected age") if child.is_premature else _("Age"))
            + ": %{customdata[1]} "
            + str(_("days"))
            + "<extra>%{fullData.name}</extra>",
        )
    ]
    low, high = max(0, min(ages) - 7), max(0, max(ages) + 7)
    for sex, title, color, dash in (
        ("boy", _("Boys - WHO median"), "#8f80a7", "dash"),
        ("girl", _("Girls - WHO median"), "#b28e6c", "dot"),
    ):
        if percentile_model:
            from datetime import timedelta

            points = [
                (age.days, value)
                for age, value in percentile_model.objects.filter(
                    sex=sex,
                    age_in_days__gte=timedelta(days=low),
                    age_in_days__lte=timedelta(days=high),
                )
                .order_by("age_in_days")
                .values_list("age_in_days", "p50_" + field)
            ]
        else:
            points = [
                (day, value) for day, value in bmi_medians()[sex] if low <= day <= high
            ]
        if not points:
            continue
        x, y = [], []
        for day, value in points:
            # WHO changes from recumbent length to standing height at age two.
            if metric in ("height", "bmi") and day == 731 and x:
                x.append(None)
                y.append(None)
            x.append(day / scale)
            y.append(display(value))
        traces.append(
            go.Scatter(
                name=str(title),
                x=x,
                y=y,
                mode="lines",
                meta={"reference": sex},
                visible=sex in references,
                showlegend=True,
                line={"color": color, "width": 2, "dash": dash},
                connectgaps=False,
                hovertemplate="%{y:.2f} "
                + unit_label
                + "<extra>%{fullData.name}</extra>",
            )
        )
    if percentiles:
        table = bmi_percentiles() if not percentile_model else None
        for sex, label_sex, color in (
            ("boy", _("Boys"), "#8f80a7"),
            ("girl", _("Girls"), "#b28e6c"),
        ):
            for percentile, column, dash in (
                (3, 1, "dot"),
                (15, 2, "dash"),
                (85, 4, "dash"),
                (97, 5, "dot"),
            ):
                if percentile_model:
                    rows = [
                        (age.days, value)
                        for age, value in percentile_model.objects.filter(
                            sex=sex,
                            age_in_days__gte=timedelta(days=low),
                            age_in_days__lte=timedelta(days=high),
                        )
                        .order_by("age_in_days")
                        .values_list("age_in_days", f"p{percentile}_{field}")
                    ]
                else:
                    rows = [
                        (row[0], row[column])
                        for row in table[sex]
                        if low <= row[0] <= high
                    ]
                if not rows:
                    continue
                xs, ys = [], []
                for day, value in rows:
                    if metric in ("height", "bmi") and day == 731 and xs:
                        xs.append(None)
                        ys.append(None)
                    xs.append(day / scale)
                    ys.append(display(value))
                title = _("%(sex)s - WHO %(percentile)s percentile") % {
                    "sex": label_sex,
                    "percentile": percentile,
                }
                traces.append(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        name=title,
                        mode="lines",
                        meta={"reference": sex, "percentile": percentile},
                        visible=sex in references,
                        line={"color": color, "width": 1.3, "dash": dash},
                        connectgaps=False,
                        hovertemplate="%{y:.2f} "
                        + unit_label
                        + "<extra>%{fullData.name}</extra>",
                    )
                )
    layout = utils.default_graph_layout_options()
    layout["xaxis"].update(
        title=age_label,
        type="linear",
        range=[
            min(0, min(ages)) / scale if max(ages) < 31 else (min(ages) - 7) / scale,
            max(high, 7) / scale,
        ],
    )
    layout["yaxis"].update(title=f"{label} ({unit_label})", rangemode="normal")
    return utils.split_graph_output(
        plotly.plot(
            go.Figure(data=traces, layout=layout),
            output_type="div",
            include_plotlyjs=False,
        )
    )
