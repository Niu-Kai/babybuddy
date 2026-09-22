# -*- coding: utf-8 -*-
import datetime
import math
import re
import time


def autorangeoptions(dates, padding=43200000):
    """
    Default autorange mix and max for all graphs.
    See: https://github.com/babybuddy/babybuddy/issues/706
    :param dates: list of datetime.date objects (or ISO date strings), any order.
    :param padding: additional padding to add to the bounds.
    :return: a dict of our autorange options.
    """
    # Accept dates in either order (and ISO date strings) so a graph cannot
    # hand over swapped bounds, which Plotly silently ignores.
    stamps = sorted(int(time.mktime(_to_date(d).timetuple())) * 1000 for d in dates)
    return dict(
        {
            "minallowed": stamps[0] - padding,
            "maxallowed": stamps[-1] + padding,
        },
    )


def _to_date(value):
    if isinstance(value, str):
        return datetime.date.fromisoformat(value)
    return value


CHART_COLORS = ["#6487a7", "#8f80a7", "#b28e6c", "#71978b", "#ad7e89", "#a29b72"]
BAR_OUTLINE = {"color": "#a3afbd", "width": 1.2}


def count_axis(maximum):
    """Readable, whole-number counts with at most about seven labeled ticks."""
    target = max(1, maximum / 6)
    power = 10 ** math.floor(math.log10(target))
    step = next(value * power for value in (1, 2, 5, 10) if value * power >= target)
    return {
        "tickmode": "linear",
        "dtick": step,
        "tick0": 0,
        "tickformat": ",d",
        "rangemode": "tozero",
    }


def default_graph_layout_options():
    """
    Default layout options for all graphs.
    :returns: a dict of default options.
    """
    return {
        "height": 480,
        "autosize": True,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "color": "rgba(255, 255, 255, 1)",
            # Bootstrap 4 font family.
            "family": '-apple-system, BlinkMacSystemFont, "Segoe UI", '
            'Roboto, "Helvetica Neue", Arial, sans-serif, '
            '"Apple Color Emoji", "Segoe UI Emoji", '
            '"Segoe UI Symbol"',
            "size": 14,
        },
        "margin": {"l": 68, "r": 24, "b": 100, "t": 32},
        "colorway": CHART_COLORS,
        "template": {
            "data": {"bar": [{"type": "bar", "marker": {"line": BAR_OUTLINE}}]}
        },
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": "#1b2430",
            "bordercolor": "#94a3b8",
            "font": {"color": "#f1f5f9", "size": 15},
            "align": "left",
            "namelength": -1,
        },
        "bargap": 0.3,
        "legend": {"orientation": "h", "y": -0.18, "x": 0},
        "xaxis": {
            "automargin": True,
            "nticks": 7,
            "tickfont": {"size": 13},
            "showgrid": False,
            "title": {"font": {"color": "rgba(255, 255, 255, 0.5)"}},
            "gridcolor": "rgba(0, 0, 0, 0.25)",
            "zerolinecolor": "rgba(0, 0, 0, 0.5)",
        },
        "yaxis": {
            "automargin": True,
            "nticks": 7,
            "tickfont": {"size": 13},
            "zeroline": False,
            "title": {"font": {"color": "rgba(255, 255, 255, 0.5)"}},
            "gridcolor": "rgba(0, 0, 0, 0.25)",
            "zerolinecolor": "rgba(0, 0, 0, 0.5)",
        },
    }


def rangeselector_date():
    """
    Graph date range selectors settings for 1w, 2w, 1m, 3m, and all.
    :returns: a dict of settings for the selectors.
    """
    return {
        "bgcolor": "rgb(35, 149, 86)",
        "activecolor": "rgb(25, 108, 62)",
        "buttons": [
            {"count": 7, "label": "1w", "step": "day", "stepmode": "backward"},
            {"count": 14, "label": "2w", "step": "day", "stepmode": "backward"},
            {"count": 1, "label": "1m", "step": "month", "stepmode": "backward"},
            {"count": 3, "label": "3m", "step": "month", "stepmode": "backward"},
            {"step": "all"},
        ],
    }


def rangeselector_time():
    """
    Graph time range selectors settings for 12h, 24h, 48h, 3d and all.
    :returns: a dict of settings for the selectors.
    """
    return {
        "bgcolor": "rgb(35, 149, 86)",
        "activecolor": "rgb(25, 108, 62)",
        "buttons": [
            {"count": 12, "label": "12h", "step": "hour", "stepmode": "backward"},
            {"count": 24, "label": "24h", "step": "hour", "stepmode": "backward"},
            {"count": 48, "label": "48h", "step": "hour", "stepmode": "backward"},
            {"count": 3, "label": "3d", "step": "day", "stepmode": "backward"},
            {"count": 7, "label": "7d", "step": "day", "stepmode": "backward"},
            {"step": "all"},
        ],
    }


def split_graph_output(output):
    """
    Split out of a Plotly graph in to html and javascript.
    :param output: a string of html and javascript comprising the graph.
    :returns: a tuple of the graph's html and javascript.
    """
    # Keep the complete wrapper here; its closing tag must not travel with
    # the scripts to the bottom of the page and swallow subsequent panels.
    scripts = re.findall(r"<script\b[^>]*>.*?</script>", output, flags=re.DOTALL)
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", output, flags=re.DOTALL)
    return html, "\n".join(scripts)


def plot_payloads(script):
    """Read JSON arguments from Plotly's generated calls, without evaluating JS."""
    import json

    decoder = json.JSONDecoder()
    plots = []
    pattern = re.compile(r"Plotly\.newPlot\(\s*")
    offset = 0
    while match := pattern.search(script or "", offset):
        cursor = match.end()
        arguments = []
        for index in range(4):
            while cursor < len(script) and script[cursor].isspace():
                cursor += 1
            value, cursor = decoder.raw_decode(script, cursor)
            arguments.append(value)
            while cursor < len(script) and script[cursor].isspace():
                cursor += 1
            if index < 3:
                if script[cursor] != ",":
                    raise ValueError("Invalid Plotly arguments")
                cursor += 1
        offset = cursor
        identifier, data, layout, config = arguments
        if (
            not isinstance(identifier, str)
            or not isinstance(data, list)
            or not isinstance(layout, dict)
            or not isinstance(config, dict)
        ):
            raise ValueError("Invalid Plotly payload")
        plots.append(dict(id=identifier, data=data, layout=layout, config=config))
    return plots
