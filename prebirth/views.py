from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, F, Min, Max
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from babybuddy.mixins import PermissionRequiredMixin
from .forms import PlanForm, ChecklistForm
from .models import Plan, ChecklistItem, Contraction


def integer_id(value):
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise Http404
    if value < 1 or value >= 2**63:
        raise Http404
    return value


def contraction_state():
    # Include the previous row beyond the displayed set to calculate its gap.
    records = list(Contraction.objects.order_by("-start", "-pk")[:51])
    now = timezone.now()
    rows = []
    for index, entry in enumerate(records[:50]):
        previous = records[index + 1] if index + 1 < len(records) else None
        rows.append(
            {
                "id": entry.pk,
                "start": entry.start.isoformat(),
                "end": entry.end.isoformat() if entry.end else None,
                "duration": entry.duration,
                "interval": (
                    (entry.start - previous.start).total_seconds() if previous else None
                ),
                "notes": entry.notes,
            }
        )
    recent = Contraction.objects.filter(
        start__gte=now - timedelta(hours=1), start__lte=now
    ).aggregate(
        count=Count("pk"),
        duration=Avg(F("end") - F("start")),
        first=Min("start"),
        last=Max("start"),
    )
    return {
        "now": now.isoformat(),
        "records": rows,
        "active": next((row for row in rows if not row["end"]), None),
        "count": recent["count"],
        "average_duration": (
            recent["duration"].total_seconds()
            if recent["duration"] is not None
            else None
        ),
        "average_interval": (
            (recent["last"] - recent["first"]).total_seconds() / (recent["count"] - 1)
            if recent["count"] > 1
            else None
        ),
    }


class Preparation(PermissionRequiredMixin, TemplateView):
    permission_required = "prebirth.view_plan"
    template_name = "prebirth/preparation.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plan = Plan.objects.filter(pk=1).first() or Plan()
        items = (
            list(ChecklistItem.objects.all())
            if self.request.user.has_perm("prebirth.view_checklistitem")
            else []
        )
        context.update(
            plan_form=PlanForm(instance=plan),
            checklist_form=ChecklistForm(),
            checklist_groups=[
                {
                    "label": label,
                    "items": [item for item in items if item.category == category],
                }
                for category, label in ChecklistItem.CATEGORIES
            ],
            packed=sum(item.packed for item in items),
            total=len(items),
            contractions=(
                contraction_state()
                if self.request.user.has_perm("prebirth.view_contraction")
                else None
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        permission = {
            "save-plan": "change_plan",
            "add-item": "add_checklistitem",
            "toggle-item": "change_checklistitem",
            "delete-item": "delete_checklistitem",
        }.get(action)
        if not permission:
            return JsonResponse({"error": _("Unknown action.")}, status=400)
        if not request.user.has_perm("prebirth." + permission):
            raise PermissionDenied
        context = self.get_context_data()
        if action == "save-plan":
            plan = Plan.objects.filter(pk=1).first() or Plan()
            form = PlanForm(request.POST, instance=plan)
            if not form.is_valid():
                context["plan_form"] = form
                return self.render_to_response(context, status=400)
            form.save()
        elif action == "add-item":
            form = ChecklistForm(request.POST)
            if not form.is_valid():
                context["checklist_form"] = form
                return self.render_to_response(context, status=400)
            form.save()
        else:
            item = get_object_or_404(
                ChecklistItem, pk=integer_id(request.POST.get("id"))
            )
            if action == "delete-item":
                item.delete()
            else:
                # Explicit desired state makes repeated requests idempotent.
                item.packed = request.POST.get("packed") == "1"
                item.save(update_fields=["packed"])
        if request.headers.get("Accept") == "application/json":
            return JsonResponse(
                {
                    "ok": True,
                    "packed": ChecklistItem.objects.filter(packed=True).count(),
                    "total": ChecklistItem.objects.count(),
                }
            )
        return redirect("prebirth:preparation")


class Contractions(PermissionRequiredMixin, View):
    permission_required = ("prebirth.view_plan", "prebirth.view_contraction")

    def get(self, request):
        return JsonResponse(contraction_state())

    def post(self, request):
        action = request.POST.get("action")
        required = {
            "start": "add_contraction",
            "stop": "change_contraction",
            "delete": "delete_contraction",
        }.get(action)
        if required is None:
            return JsonResponse({"error": _("Unknown action.")}, status=400)
        if not request.user.has_perm("prebirth." + required):
            raise PermissionDenied
        if action == "start":
            # get_or_create retries a concurrent unique-constraint conflict.
            # Avoid a read-then-write outer transaction that can lock SQLite.
            plan, _created = Plan.objects.get_or_create(pk=1)
            Contraction.objects.get_or_create(
                plan=plan, end=None, defaults={"created_by": request.user}
            )
        elif action == "stop":
            notes = request.POST.get("notes", "")
            if len(notes) > 1000:
                return JsonResponse(
                    {"error": _("Keep contraction notes under 1,000 characters.")},
                    status=400,
                )
            contraction = get_object_or_404(
                Contraction, pk=integer_id(request.POST.get("id"))
            )
            Contraction.objects.filter(pk=contraction.pk, end__isnull=True).update(
                end=timezone.now(), notes=notes
            )
        else:
            get_object_or_404(
                Contraction, pk=integer_id(request.POST.get("id"))
            ).delete()
        return JsonResponse(contraction_state())
