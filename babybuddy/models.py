# -*- coding: utf-8 -*-
import zoneinfo

from django.core.exceptions import ValidationError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy

from rest_framework.authtoken.models import Token

# Entries in tzdata that are not real zones and must not be offered to users.
TIMEZONE_EXCLUDES = {"Factory", "localtime", "posixrules"}


def timezone_choices():
    """Time zones the running host can actually load, as form choices."""
    names = sorted(zoneinfo.available_timezones() - TIMEZONE_EXCLUDES)
    return [(name, name) for name in names]


def validate_timezone(value):
    if value in TIMEZONE_EXCLUDES:
        raise ValidationError(
            _("%(value)s is not a valid time zone."), params={"value": value}
        )
    try:
        zoneinfo.ZoneInfo(value)
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        raise ValidationError(
            _("%(value)s is not a valid time zone."), params={"value": value}
        )


# Dashboard cards a user can hide (see Settings.dashboard_hidden_cards).
DASHBOARD_CARDS = [
    ("feeding_last", _("Last Feeding")),
    ("diaperchange_last", _("Last Diaper Change")),
    ("sleep_last", _("Last Sleep")),
    ("pumping_overview", _("Pumping & nursing")),
    ("medication_last", _("Last Medication")),
    ("sleep_naps_day", _("Today's Naps")),
    ("tummytime_day", _("Today's Tummy Time")),
    ("timer_list", _("Timers")),
    ("feeding_recent", _("Recent Feedings")),
    ("feeding_last_method", _("Last Feeding Method")),
    ("sleep_recent", _("Recent Sleep")),
    ("statistics", _("Statistics")),
    ("diaperchange_types", _("Diaper Changes")),
    ("breastfeeding", _("Breastfeeding")),
    ("notes_recent", _("Recent Notes")),
    ("appointments_upcoming", _("Upcoming Appointments")),
    ("tags_last", _("Time Since Tag")),
    ("bathtime_last", _("Last Bath")),
    ("reflux_last", _("Last Reflux")),
    ("food_recent", _("Recent Foods")),
]


DASHBOARD_CARDS += [
    ("measurement_weight", _("Latest weight")),
    ("measurement_height", _("Latest height")),
    ("measurement_head_circumference", _("Latest head circumference")),
    ("measurement_bmi", _("Calculated BMI")),
    ("measurement_temperature", _("Latest temperature")),
]
DEFAULT_DASHBOARD_CARDS = {
    "pumping_overview",
    "feeding_last",
    "diaperchange_last",
    "sleep_last",
    "timer_list",
    "appointments_upcoming",
    "measurement_weight",
    "measurement_height",
}


def default_hidden_dashboard_cards():
    return [key for key, label in DASHBOARD_CARDS if key not in DEFAULT_DASHBOARD_CARDS]


class Settings(models.Model):
    hidden_activities = models.JSONField(default=list, blank=True)
    hidden_entry_fields = models.JSONField(default=list, blank=True)
    restrict_children = models.BooleanField(default=False)
    allowed_children = models.ManyToManyField(
        "core.Child", blank=True, related_name="authorized_settings"
    )
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    pumping_reminder_minutes = models.PositiveIntegerField(null=True, blank=True)
    pumping_reminder_basis = models.CharField(
        max_length=20,
        default="combined",
        choices=[("combined", _("Pumping or nursing")), ("pumping", _("Pumping only"))],
    )
    dashboard_refresh_rate = models.DurationField(
        verbose_name=_("Refresh rate"),
        help_text=_(
            "If supported by browser, the dashboard will only refresh when visible, and also when receiving focus."
        ),
        blank=True,
        null=True,
        default=timezone.timedelta(minutes=1),
        choices=[
            (None, _("disabled")),
            (
                timezone.timedelta(minutes=1),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 1)
                % {"minutes": 1},
            ),
            (
                timezone.timedelta(minutes=2),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 2)
                % {"minutes": 2},
            ),
            (
                timezone.timedelta(minutes=3),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 3)
                % {"minutes": 3},
            ),
            (
                timezone.timedelta(minutes=4),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 4)
                % {"minutes": 4},
            ),
            (
                timezone.timedelta(minutes=5),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 5)
                % {"minutes": 5},
            ),
            (
                timezone.timedelta(minutes=10),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 10)
                % {"minutes": 10},
            ),
            (
                timezone.timedelta(minutes=15),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 15)
                % {"minutes": 15},
            ),
            (
                timezone.timedelta(minutes=30),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 30)
                % {"minutes": 30},
            ),
        ],
    )
    dashboard_hide_empty = models.BooleanField(
        verbose_name=_("Hide Empty Dashboard Cards"), default=False, editable=True
    )
    dashboard_hide_age = models.DurationField(
        verbose_name=_("Hide data older than"),
        help_text=_(
            "This setting controls which data will be shown " "in the dashboard."
        ),
        blank=True,
        null=True,
        default=None,
        choices=[
            (None, _("show all data")),
            (
                timezone.timedelta(days=1),
                ngettext_lazy("%(days)d day", "%(days)d days", 1) % {"days": 1},
            ),
            (
                timezone.timedelta(days=2),
                ngettext_lazy("%(days)d day", "%(days)d days", 2) % {"days": 2},
            ),
            (
                timezone.timedelta(days=3),
                ngettext_lazy("%(days)d day", "%(days)d days", 3) % {"days": 3},
            ),
            (
                timezone.timedelta(weeks=1),
                ngettext_lazy("%(weeks)d week", "%(weeks)d weeks", 1) % {"weeks": 1},
            ),
            (
                timezone.timedelta(weeks=4),
                ngettext_lazy("%(weeks)d week", "%(weeks)d weeks", 4) % {"weeks": 4},
            ),
        ],
    )
    language = models.CharField(
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        max_length=255,
        verbose_name=_("Language"),
    )
    liquid_unit = models.CharField(
        max_length=10,
        default="mL",
        choices=[("mL", "mL"), ("fl oz", _("fl oz (US)"))],
        verbose_name=_("Liquid"),
    )
    length_unit = models.CharField(
        max_length=10,
        default="cm",
        choices=[("cm", "cm"), ("in", "in")],
        verbose_name=_("Length"),
    )
    weight_unit = models.CharField(
        max_length=10,
        default="kg",
        choices=[("kg", "kg"), ("lb", "lbs"), ("oz", "oz")],
        verbose_name=_("Weight"),
    )
    temperature_unit = models.CharField(
        max_length=10,
        default="C",
        choices=[("C", "°C"), ("F", "°F")],
        verbose_name=_("Temperature"),
    )
    theme = models.CharField(
        choices=[
            ("auto", _("Match device")),
            ("light", _("Light")),
            ("dark", _("Dark")),
        ],
        default="dark",
        max_length=255,
        verbose_name=_("Theme"),
    )
    # No `choices` here on purpose: the zone list depends on the host's tzdata,
    # so baking it into a migration made every host with a different tzdata
    # report "models have changes not reflected in a migration" (#984) and let
    # users pick zones the server could not load (#1003). The settings form
    # offers the runtime list and `validate_timezone` guards the value.
    timezone = models.CharField(
        default=timezone.get_default_timezone_name,
        max_length=100,
        validators=[validate_timezone],
        verbose_name=_("Timezone"),
    )
    pagination_count = models.PositiveIntegerField(
        choices=[
            (10, _("%(count)d Per Page") % {"count": 10}),
            (25, _("%(count)d Per Page") % {"count": 25}),
            (50, _("%(count)d Per Page") % {"count": 50}),
            (100, _("%(count)d Per Page") % {"count": 100}),
            (250, _("%(count)d Per Page") % {"count": 250}),
            (0, _("Show All")),
        ],
        default=25,
        verbose_name=_("Items Per Page"),
    )
    use_24_hour_time = models.BooleanField(
        default=False,
        verbose_name=_("24-hour clock"),
        help_text=_("Show times as 13:05 instead of 1:05 p.m."),
    )
    timezone_follow_device = models.BooleanField(
        default=False,
        verbose_name=_("Use the device's time zone"),
        help_text=_(
            "Follow the time zone of the browser or phone in use, e.g. while "
            "travelling, instead of the fixed time zone above."
        ),
    )
    dashboard_hidden_cards = models.JSONField(
        blank=True,
        default=default_hidden_dashboard_cards,
        verbose_name=_("Hidden dashboard cards"),
    )
    dashboard_card_order = models.JSONField(blank=True, default=list)
    access_expires = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_(
            "Optional. After this time the user can no longer sign in or use "
            "the API."
        ),
        verbose_name=_("Access expires"),
    )

    def __str__(self):
        return str(format_lazy(_("{user}'s Settings"), user=self.user))

    def api_key(self, reset=False):
        """
        Get or create an API key for the associated user.
        :param reset: If True, delete the existing key and create a new one.
        :return: The user's API key.
        """
        if reset:
            Token.objects.get(user=self.user).delete()
        return Token.objects.get_or_create(user=self.user)[0]

    @property
    def access_expired(self):
        return self.access_expires is not None and self.access_expires <= timezone.now()

    @property
    def dashboard_refresh_rate_milliseconds(self):
        """
        Convert seconds to milliseconds to be used in a Javascript setInterval
        function call.
        :return: the refresh rate in milliseconds or None.
        """
        if self.dashboard_refresh_rate:
            return self.dashboard_refresh_rate.seconds * 1000
        return None


def access_expired(user):
    """
    Check if a user's access has expired.
    :param user: The user to check.
    :return: True if the user has an access expiry time that has passed.
    """
    try:
        return user.settings.access_expired
    except Settings.DoesNotExist:
        return False


@receiver(post_save, sender=get_user_model())
def create_user_settings(sender, instance, created, **kwargs):
    if created:
        Settings.objects.create(user=instance)


@receiver(post_save, sender=get_user_model())
def save_user_settings(sender, instance, **kwargs):
    instance.settings.save()


class OfflineReceipt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField()
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"], name="offline_user_key_unique"
            )
        ]


class ImportBatch(models.Model):
    """Private staged CSV and durable receipt for an explicitly confirmed import."""

    import uuid

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64)
    options = models.JSONField(default=dict)
    rows = models.JSONField(default=list)
    count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "digest"], name="import_user_digest_unique"
            )
        ]
