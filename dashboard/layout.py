from django.utils.translation import gettext_lazy as _
from babybuddy.models import DASHBOARD_CARDS

PERMISSIONS = {
    "feeding_last": "feeding",
    "diaperchange_last": "diaperchange",
    "sleep_last": "sleep",
    "pumping_last": "pumping",
    "medication_last": "medication",
    "sleep_naps_day": "sleep",
    "tummytime_day": "tummytime",
    "timer_list": "timer",
    "feeding_recent": "feeding",
    "feeding_last_method": "feeding",
    "sleep_recent": "sleep",
    "pumping_recent": "pumping",
    "diaperchange_types": "diaperchange",
    "breastfeeding": "feeding",
    "notes_recent": "note",
    "appointments_upcoming": "appointment",
    "tags_last": "tag",
    "bathtime_last": "bathtime",
    "reflux_last": "reflux",
    "food_recent": "food",
    "statistics": "child",
    "measurement_weight": "weight",
    "measurement_height": "height",
    "measurement_head_circumference": "headcircumference",
    "measurement_bmi": "bmi",
    "measurement_temperature": "temperature",
}
GLANCE = [
    "feeding_last",
    "diaperchange_last",
    "sleep_last",
    "timer_list",
    "appointments_upcoming",
    "pumping_last",
    "medication_last",
    "sleep_naps_day",
    "tummytime_day",
    "bathtime_last",
    "reflux_last",
    "food_recent",
    "tags_last",
]
TRENDS = [
    "feeding_recent",
    "feeding_last_method",
    "sleep_recent",
    "pumping_recent",
    "statistics",
    "diaperchange_types",
    "breastfeeding",
    "notes_recent",
]
MEASUREMENTS = [key for key, label in DASHBOARD_CARDS if key.startswith("measurement_")]


def allowed(user, key):
    return user.has_perm("core.view_" + PERMISSIONS[key])


def sections(user):
    hidden = set(user.settings.dashboard_hidden_cards or [])
    return [
        {"key": key, "label": label, "panels": selected}
        for key, label, keys in (
            ("glance", _("At a glance"), GLANCE),
            ("trends", _("Trends"), TRENDS),
        )
        if (
            selected := [
                panel for panel in keys if panel not in hidden and allowed(user, panel)
            ]
        )
    ]
