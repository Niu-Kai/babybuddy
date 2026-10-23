"""Optional milk-feeding prompts, never a feeding prescription or closed-app alarm."""

from datetime import timedelta

from django import forms
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from babybuddy.mixins import PermissionRequiredMixin
from core.access import scoped
from core.models import Child, Feeding, FeedingReminder, Timer

MILK_TYPES = ("breast milk", "fortified breast milk", "formula")


def age_suggestion(child, milk, today=None):
    """Conservative editable starting points within CDC ranges; stop at six months.

    The CDC gives ranges, not these exact midpoint reminder intervals. Months
    use calendar arithmetic so the suggestion stops at the six-month birthday.
    """
    from dateutil.relativedelta import relativedelta

    today = today or timezone.localdate()
    age = (today - child.birth_date).days
    if age < 0:
        return None, _("Reminders begin after birth.")
    if child.due_date and (child.due_date - child.birth_date).days > 21:
        return None, _(
            "For a baby born before 37 weeks, use your care team's interval."
        )
    if today >= child.birth_date + relativedelta(months=6):
        return None, _(
            "From 6 months, follow feeding cues and choose your own interval."
        )
    if age < 7:
        return 150, _("First days: newborns commonly feed 8–12 times in 24 hours.")
    if milk == "formula":
        return 210, _(
            "First weeks and months: formula feedings are often 3–4 hours apart."
        )
    return (150 if age < 28 else 180), _(
        "First weeks and months: breastfed babies often feed every 2–4 hours, about 8–12 times in 24 hours."
    )


class ReminderForm(forms.ModelForm):
    class Meta:
        model = FeedingReminder
        fields = ("enabled", "milk", "mode", "minutes")
        labels = {
            "enabled": _("Remind me"),
            "milk": _("Milk"),
            "mode": _("Interval"),
            "minutes": _("Custom interval (minutes)"),
        }
        widgets = {
            "milk": forms.Select(attrs={"class": "form-select"}),
            "mode": forms.Select(
                attrs={"class": "form-select", "data-reminder-mode": ""}
            ),
            "minutes": forms.NumberInput(attrs={"class": "form-control", "step": 15}),
            "enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("enabled"):
            if data.get("mode") == "custom" and not data.get("minutes"):
                self.add_error("minutes", _("Enter a reminder interval."))
            if (
                data.get("mode") == "age"
                and age_suggestion(self.instance.child, data.get("milk"))[0] is None
            ):
                self.add_error("mode", _("Choose a custom interval for this age."))
        return data


def reminders_for(user, *, enabled_only=False):
    """Read permitted children and feeding state in a bounded set of queries."""
    now = timezone.now()
    milk = Feeding.objects.filter(
        Q(type__in=MILK_TYPES) | Q(secondary_type__in=MILK_TYPES),
        child_id=OuterRef("pk"),
        start__lte=now,
    )
    topups = Feeding.objects.filter(
        child_id=OuterRef("pk"),
        top_up_at__lte=now,
        top_up_type__in=MILK_TYPES,
    )
    counts = (
        milk.filter(start__gte=now - timedelta(hours=24))
        .order_by()
        .values("child_id")
        .annotate(total=Count("pk"))
    )
    plans_query = scoped(FeedingReminder.objects.filter(user=user), user)
    if enabled_only:
        plans_query = plans_query.filter(enabled=True)
    plans = {plan.child_id: plan for plan in plans_query}
    if enabled_only and not plans:
        return
    active = set(
        scoped(Timer.objects.filter(context__activity="feeding"), user).values_list(
            "child_id", flat=True
        )
    )
    children = scoped(Child.objects.all(), user)
    if enabled_only:
        children = children.filter(pk__in=plans)
    children = children.annotate(
        last_milk_start=Subquery(milk.order_by("-start", "-pk").values("start")[:1]),
        last_topup_start=Subquery(
            topups.order_by("-top_up_at", "-pk").values("top_up_at")[:1]
        ),
        milk_count=Subquery(counts.values("total")[:1]),
    ).order_by("first_name", "last_name", "pk")
    for child in children:
        plan = plans.get(child.pk) or FeedingReminder(user=user, child=child)
        if enabled_only and not plan.enabled:
            continue
        suggestion, guidance = age_suggestion(child, plan.milk)
        interval = plan.minutes if plan.mode == "custom" else suggestion
        references = [
            at for at in (child.last_milk_start, child.last_topup_start) if at
        ]
        reference = max(references, default=None)
        due = (
            reference + timedelta(minutes=interval) if reference and interval else None
        )
        if (
            due
            and plan.snoozed_until
            and plan.snoozed_reference == reference
            and plan.snoozed_until > due
        ):
            due = plan.snoozed_until
        born = child.birth_date <= timezone.localdate()
        yield {
            "child": child,
            "plan": plan,
            "suggestion": suggestion,
            "guidance": guidance,
            "interval": interval,
            "reference": reference,
            "due": due if born else None,
            "ready": bool(
                born and plan.enabled and due and due <= now and child.pk not in active
            ),
            "active": child.pk in active,
            "count": child.milk_count or 0,
            "review": bool(born and plan.enabled and not interval),
        }


class Reminders(PermissionRequiredMixin, TemplateView):
    permission_required = ("core.view_feeding", "core.view_child")
    template_name = "core/feeding_reminders.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = list(reminders_for(self.request.user))
        from core.presentation import presentation

        selected = presentation(self.request)["selected_child"]
        if selected:
            rows = [row for row in rows if row["child"].pk == selected.pk]
        for row in rows:
            row["form"] = ReminderForm(
                instance=row["plan"], prefix=str(row["child"].pk)
            )
        context["reminders"] = rows
        return context

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(
            scoped(Child.objects.all(), request.user),
            pk=identifier(request.POST.get("child")),
        )
        plan = FeedingReminder.objects.filter(user=request.user, child=child).first()
        plan = plan or FeedingReminder(user=request.user, child=child)
        form = ReminderForm(request.POST, instance=plan, prefix=str(child.pk))
        if form.is_valid():
            FeedingReminder.objects.update_or_create(
                user=request.user,
                child=child,
                defaults={
                    **{key: form.cleaned_data[key] for key in form.Meta.fields},
                    "snoozed_until": None,
                    "snoozed_reference": None,
                },
            )
            return redirect("core:feeding-reminders")
        context = self.get_context_data()
        for row in context["reminders"]:
            if row["child"].pk == child.pk:
                row["form"] = form
        return self.render_to_response(context)


class ReminderStatus(PermissionRequiredMixin, View):
    permission_required = ("core.view_feeding", "core.view_child")

    def get(self, request):
        rows = []
        for row in reminders_for(request.user, enabled_only=True):
            plan, child = row["plan"], row["child"]
            rows.append(
                {
                    "id": plan.pk,
                    "child": str(child),
                    "ready": row["ready"],
                    "review": row["review"],
                    "due": row["due"].isoformat() if row["due"] else None,
                    "reference": (
                        row["reference"].isoformat() if row["reference"] else None
                    ),
                    "url": (
                        reverse("core:feeding-reminders")
                        + "?scope="
                        + child.slug
                        + "#child-"
                        + str(child.pk)
                        if row["review"]
                        else reverse("core:feeding-add") + "?child=" + child.slug
                    ),
                }
            )
        return JsonResponse({"reminders": rows, "now": timezone.now().isoformat()})

    def post(self, request):
        plan = get_object_or_404(
            scoped(FeedingReminder.objects.filter(user=request.user), request.user),
            pk=identifier(request.POST.get("id")),
        )
        row = next(
            (
                row
                for row in reminders_for(request.user, enabled_only=True)
                if row["plan"].pk == plan.pk
            ),
            None,
        )
        if not row or not row["ready"]:
            return JsonResponse({"ok": False}, status=409)
        plan.snoozed_reference = row["reference"]
        plan.snoozed_until = timezone.now() + timedelta(minutes=10)
        plan.save(update_fields=["snoozed_until", "snoozed_reference"])
        return JsonResponse({"ok": True})


def identifier(value):
    try:
        value = int(value)
        if 0 < value < 2**63:
            return value
    except (TypeError, ValueError):
        pass
    raise Http404
