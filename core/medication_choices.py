"""Only the selected child's permitted medication history is suggested."""

from django.http import JsonResponse
from django.db.models import OuterRef, Subquery
from django.views import View
from babybuddy.mixins import PermissionRequiredMixin
from core.models import Medication, Child
from core.access import scoped


class MedicationChoices(PermissionRequiredMixin, View):
    permission_required = ("core.view_medication",)

    def get(self, request):
        try:
            child = scoped(Child.objects.all(), request.user).get(
                pk=request.GET.get("child")
            )
        except (ValueError, TypeError, OverflowError, Child.DoesNotExist):
            return JsonResponse({"medications": []})
        latest = (
            Medication.objects.filter(child=child, name=OuterRef("name"))
            .order_by("-time", "-pk")
            .values("pk")[:1]
        )
        rows = Medication.objects.filter(child=child, pk=Subquery(latest)).order_by(
            "name"
        )[:200]
        return JsonResponse(
            {
                "medications": [
                    {
                        "name": row.name,
                        "dosage": row.dosage,
                        "dosage_unit": row.dosage_unit,
                        "next_dose_interval": (
                            row.next_dose_interval.total_seconds() / 3600
                            if row.next_dose_interval
                            else None
                        ),
                    }
                    for row in rows
                ]
            }
        )
