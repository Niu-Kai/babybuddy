# -*- coding: utf-8 -*-
"""
Per-request display preferences that template filters cannot reach through
the request object (they have no access to it). Set by
`babybuddy.middleware.UserTimezoneMiddleware`.
"""

import threading

_local = threading.local()


def set_time_format(value):
    """A Django time format string (e.g. "H:i") or None for the locale's."""
    _local.time_format = value


def get_time_format():
    return getattr(_local, "time_format", None)
