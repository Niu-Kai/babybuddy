# -*- coding: utf-8 -*-
import datetime
import time


def autorangeoptions(dates, padding=10000000):
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


def default_graph_layout_options():
    """
    Default layout options for all graphs.
    :returns: a dict of default options.
    """
    return {
        "paper_bgcolor": "rgb(52, 58, 64)",
        "plot_bgcolor": "rgb(52, 58, 64)",
        "font": {
            "color": "rgba(255, 255, 255, 1)",
            # Bootstrap 4 font family.
            "family": '-apple-system, BlinkMacSystemFont, "Segoe UI", '
            'Roboto, "Helvetica Neue", Arial, sans-serif, '
            '"Apple Color Emoji", "Segoe UI Emoji", '
            '"Segoe UI Symbol"',
            "size": 14,
        },
        "margin": {"b": 80, "t": 80},
        "xaxis": {
            "title": {"font": {"color": "rgba(255, 255, 255, 0.5)"}},
            "gridcolor": "rgba(0, 0, 0, 0.25)",
            "zerolinecolor": "rgba(0, 0, 0, 0.5)",
        },
        "yaxis": {
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
    html, js = output.split("<script")
    js = "<script" + js
    return html, js
