from decimal import ROUND_CEILING
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, ngettext

from .sizing import DIAPER_SIZES
from .forecast import NOTICE_DAYS, RESTOCK_DAYS

CLOTHING_SIZES = [
    "Preemie",
    "Newborn",
    "0–3 months",
    "3–6 months",
    "6–9 months",
    "9–12 months",
    "12–18 months",
    "18–24 months",
    "2T",
    "3T",
    "4T",
    "5T",
]


class ChildSupplyProfile(models.Model):
    child = models.OneToOneField(
        "core.Child", on_delete=models.CASCADE, related_name="supply_profile"
    )
    diaper_size = models.CharField(max_length=40, blank=True)
    clothing_size = models.CharField(max_length=40, blank=True)
    auto_deduct_diapers = models.BooleanField(
        _("Deduct diapers automatically"), default=True
    )
    diaper_stock = models.ForeignKey(
        "StockItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diaper_users",
        verbose_name=_("Diaper supply"),
    )

    def __str__(self):
        return str(self.child)


class StockItem(models.Model):
    CATEGORIES = [
        ("diapers", _("Diapers")),
        ("wipes", _("Wipes")),
        ("feeding", _("Feeding supplies")),
        ("formula", _("Formula")),
        ("food", _("Food")),
        ("clothing", _("Clothing")),
        ("bath", _("Bath & skin care")),
        ("health", _("Health supplies")),
        ("other", _("Other")),
    ]
    UNITS = [
        ("items", _("items")),
        ("diapers", _("diapers")),
        ("wipes", _("wipes")),
        ("packs", _("packs")),
        ("cans", _("cans")),
        ("bottles", _("bottles")),
        ("mL", "mL"),
        ("fl oz", "fl oz"),
        ("g", "g"),
        ("oz", "oz"),
    ]
    STAGES = [
        ("current", _("Use now")),
        ("next", _("Next size / later")),
        ("outgrown", _("Outgrown / no longer used")),
    ]
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="other")
    size = models.CharField(max_length=40, blank=True)
    stage = models.CharField(max_length=12, choices=STAGES, default="current")
    unit = models.CharField(max_length=12, choices=UNITS, default="items")
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, editable=False
    )
    expiration_date = models.DateField(_("Batch expiration"), null=True, blank=True)
    min_age_months = models.PositiveSmallIntegerField(
        _("Minimum age (months)"), null=True, blank=True
    )
    max_age_months = models.PositiveSmallIntegerField(
        _("Maximum age (months)"), null=True, blank=True
    )
    notes = models.TextField(blank=True)
    archived = models.BooleanField(default=False)
    snoozed_until = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0), name="stock_nonnegative"
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if (
            self.min_age_months is not None
            and self.max_age_months is not None
            and self.min_age_months > self.max_age_months
        ):
            errors["max_age_months"] = _(
                "Maximum age must be at least the minimum age."
            )
        if errors:
            raise ValidationError(errors)

    def display_unit(self, count):
        return {
            "items": lambda: ngettext("item", "items", count),
            "diapers": lambda: ngettext("diaper", "diapers", count),
            "wipes": lambda: ngettext("wipe", "wipes", count),
            "packs": lambda: ngettext("pack", "packs", count),
            "cans": lambda: ngettext("can", "cans", count),
            "bottles": lambda: ngettext("bottle", "bottles", count),
        }.get(self.unit, lambda: self.unit)()

    def quantity_unit(self):
        return self.display_unit(self.quantity)

    def buy_unit(self):
        return self.display_unit(self.buy_quantity or 0)

    @property
    def reminder_label(self):
        # Preserve reminder keys used by integrations and filtering.
        return {
            "Expired": _("Expired"),
            "Out of stock": _("Out of stock"),
            "Expiring soon": _("Expiring soon"),
            "Running low": _("Running low"),
        }.get(self.reminder, "")

    @property
    def fit(self):
        return self.stage

    @property
    def fit_label(self):
        return {
            "current": _("Use now"),
            "next": _("Next size / later"),
            "outgrown": _("Outgrown"),
            "review": _("Check size"),
        }[self.fit]

    @property
    def daily_use_rate(self):
        if hasattr(self, "_daily_use_rate"):
            return self._daily_use_rate
        from .forecast import daily_rates

        # Most callers use the request-scoped snapshot. Direct model consumers
        # still account for every supply when checking ambiguous assignments.
        return daily_rates(type(self).objects.all()).get(self.pk)

    @property
    def days_left(self):
        rate = self.daily_use_rate
        return (
            int((self.quantity / rate).to_integral_value(rounding=ROUND_CEILING))
            if rate
            else None
        )

    @property
    def expired(self):
        return bool(
            self.expiration_date and self.expiration_date < timezone.localdate()
        )

    @property
    def reminder(self):
        if self.archived or self.fit != "current":
            return ""
        if self.expired and self.quantity > 0:
            return "Expired"
        if self.quantity <= 0:
            return "Out of stock"
        if (
            self.expiration_date
            and (self.expiration_date - timezone.localdate()).days <= NOTICE_DAYS
        ):
            return "Expiring soon"
        if self.days_left is not None and self.days_left <= NOTICE_DAYS:
            return "Running low"
        return ""

    @property
    def snoozed(self):
        return bool(self.snoozed_until and self.snoozed_until > timezone.localdate())

    @property
    def alert(self):
        if self.snoozed:
            return ""
        return self.reminder

    @property
    def buy_quantity(self):
        rate = self.daily_use_rate
        return (
            (rate * RESTOCK_DAYS).to_integral_value(rounding=ROUND_CEILING)
            if rate
            else None
        )


class StockMovement(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="movements"
    )
    action = models.CharField(
        max_length=10,
        choices=[
            ("add", _("Restocked")),
            ("use", _("Used")),
            ("set", _("Count corrected")),
        ],
    )
    change = models.DecimalField(max_digits=12, decimal_places=3)
    balance = models.DecimalField(max_digits=12, decimal_places=3)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["item", "action", "created_at"], name="stock_usage_time_idx"
            )
        ]
        ordering = ["-created_at", "-pk"]


class DiaperStockUsage(models.Model):
    entry = models.OneToOneField(
        "core.DiaperChange", on_delete=models.CASCADE, related_name="stock_usage"
    )
    child_id_at_save = models.PositiveIntegerField()
    item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diaper_usages",
    )
    deducted = models.BooleanField(default=False)
    status = models.CharField(max_length=20)

    class Meta:
        default_permissions = ()


class Equipment(models.Model):
    name = models.CharField(max_length=120)
    children = models.ManyToManyField("core.Child", related_name="equipment")
    weight_limit = models.FloatField(_("Maximum weight"), null=True, blank=True)
    weight_unit = models.CharField(
        max_length=4, choices=[("kg", "kg"), ("lb", "lbs"), ("oz", "oz")], default="lb"
    )
    height_limit = models.FloatField(_("Maximum height"), null=True, blank=True)
    height_unit = models.CharField(
        max_length=4, choices=[("cm", "cm"), ("in", "in")], default="in"
    )
    instructions = models.TextField(_("Other manufacturer limits"), blank=True)
    manual_review = models.BooleanField(
        _("Needs review (milestone or other limit)"), default=False
    )
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return self.name

    def clean(self):
        import math

        errors = {}
        for field in ("weight_limit", "height_limit"):
            value = getattr(self, field)
            if value is not None and (not math.isfinite(value) or value <= 0):
                errors[field] = _("Enter a positive limit.")
        if errors:
            raise ValidationError(errors)

    def assessments(self):
        from core.units import convert

        results = []
        for child in self.children.all():
            checks = []
            for metric, field, canonical in (
                ("weight", "weight", "kg"),
                ("height", "height", "cm"),
            ):
                limit = getattr(self, metric + "_limit")
                if limit is None:
                    continue
                record = (
                    getattr(child, metric)
                    .order_by(
                        *(
                            ["-date", "-time", "-pk"]
                            if metric == "weight"
                            else ["-date", "-pk"]
                        )
                    )
                    .first()
                )
                unit = getattr(self, metric + "_unit")
                value = (
                    convert(getattr(record, field), canonical, unit)
                    if record and record.entry_unit
                    else None
                )
                checks.append(
                    {
                        "metric": {"weight": _("Weight"), "height": _("Height")}[
                            metric
                        ],
                        "value": value,
                        "unit": unit,
                        "limit": limit,
                        "date": record.date if record else None,
                        "reached": value is not None and value >= limit,
                    }
                )
            reached = self.manual_review or any(check["reached"] for check in checks)
            results.append(
                {
                    "child": child,
                    "checks": checks,
                    "attention": reached,
                    "status": (
                        _("Limit reached / review before use")
                        if reached
                        else (
                            _("No measurement recorded")
                            if any(c["value"] is None for c in checks)
                            else (
                                _("Below entered limits")
                                if checks
                                else _("Check manufacturer instructions")
                            )
                        )
                    ),
                }
            )
        return results
