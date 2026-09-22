from decimal import ROUND_CEILING
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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
        "Deduct diapers automatically", default=True
    )
    diaper_stock = models.ForeignKey(
        "StockItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diaper_users",
        verbose_name="Diaper supply",
    )

    def __str__(self):
        return str(self.child)


class StockItem(models.Model):
    CATEGORIES = [
        ("diapers", "Diapers"),
        ("wipes", "Wipes"),
        ("feeding", "Feeding supplies"),
        ("formula", "Formula"),
        ("food", "Food"),
        ("clothing", "Clothing"),
        ("bath", "Bath & skin care"),
        ("health", "Health supplies"),
        ("other", "Other"),
    ]
    UNITS = [
        ("items", "items"),
        ("diapers", "diapers"),
        ("wipes", "wipes"),
        ("packs", "packs"),
        ("cans", "cans"),
        ("bottles", "bottles"),
        ("mL", "mL"),
        ("fl oz", "fl oz"),
        ("g", "g"),
        ("oz", "oz"),
    ]
    STAGES = [
        ("current", "Use now"),
        ("next", "Next size / later"),
        ("outgrown", "Outgrown / no longer used"),
    ]
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="other")
    size = models.CharField(max_length=40, blank=True)
    stage = models.CharField(max_length=12, choices=STAGES, default="current")
    unit = models.CharField(max_length=12, choices=UNITS, default="items")
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, editable=False
    )
    expiration_date = models.DateField("Batch expiration", null=True, blank=True)
    min_age_months = models.PositiveSmallIntegerField(
        "Minimum age (months)", null=True, blank=True
    )
    max_age_months = models.PositiveSmallIntegerField(
        "Maximum age (months)", null=True, blank=True
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
            errors["max_age_months"] = "Maximum age must be at least the minimum age."
        if errors:
            raise ValidationError(errors)

    def quantity_unit(self):
        return (
            self.unit[:-1]
            if self.quantity == 1
            and self.unit in {"items", "diapers", "wipes", "packs", "cans", "bottles"}
            else self.unit
        )

    def buy_unit(self):
        return (
            self.unit[:-1]
            if self.buy_quantity == 1
            and self.unit in {"items", "diapers", "wipes", "packs", "cans", "bottles"}
            else self.unit
        )

    @property
    def fit(self):
        return self.stage

    @property
    def fit_label(self):
        return {
            "current": "Use now",
            "next": "Next size / later",
            "outgrown": "Outgrown",
            "review": "Check size",
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
        choices=[("add", "Restocked"), ("use", "Used"), ("set", "Count corrected")],
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
