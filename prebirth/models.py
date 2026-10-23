from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Plan(models.Model):
    """One shared preparation area, available before any child is created."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    due_date = models.DateField(blank=True, null=True, verbose_name=_("Due date"))
    hospital = models.CharField(max_length=200, blank=True, verbose_name=_("Hospital"))
    contact = models.CharField(
        max_length=200, blank=True, verbose_name=_("Care team / contact")
    )
    phone = models.CharField(max_length=60, blank=True, verbose_name=_("Phone"))
    notes = models.TextField(
        max_length=12000,
        blank=True,
        verbose_name=_("Hospital instructions & birth preferences"),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="one_prebirth_plan")
        ]


class ChecklistItem(models.Model):
    CATEGORIES = [
        ("documents", _("Documents & essentials")),
        ("parent", _("For the birthing parent")),
        ("baby", _("For the baby")),
        ("support", _("For your support person")),
        ("home", _("Before leaving home")),
    ]
    label = models.CharField(max_length=250, verbose_name=_("Item"))
    category = models.CharField(max_length=12, choices=CATEGORIES, default="parent")
    packed = models.BooleanField(default=False)
    preset = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["category", "position", "pk"]

    @property
    def display_label(self):
        return _(self.label) if self.preset else self.label


class Contraction(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, default=1)
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(blank=True, null=True)
    notes = models.CharField(max_length=1000, blank=True, verbose_name=_("Notes"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True
    )

    class Meta:
        ordering = ["-start", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan"],
                condition=models.Q(end__isnull=True),
                name="one_active_contraction",
            ),
            models.CheckConstraint(
                condition=models.Q(end__isnull=True)
                | models.Q(end__gte=models.F("start")),
                name="contraction_end_after_start",
            ),
        ]

    @property
    def duration(self):
        return ((self.end or timezone.now()) - self.start).total_seconds()

    def clean(self):
        if self.end and self.end < self.start:
            raise ValidationError({"end": _("End time must come after start time.")})
