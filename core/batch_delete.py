"""Bounded admin deletion, scoped to the original user and selected records."""

from datetime import timedelta
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction, OperationalError
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from core.access import scoped
from core.models import DeletionBatch

BATCH_SIZE = 100
EXCLUDED = {"child", "activitytype", "bmi", "deletionbatch"}


@admin.action(
    description=_("Delete selected entries in batches"), permissions=["delete"]
)
def start_batch(model_admin, request, queryset):
    if not model_admin.has_delete_permission(request):
        raise PermissionDenied
    ids = list(
        scoped(queryset, request.user).order_by("pk").values_list("pk", flat=True)
    )
    if not ids:
        model_admin.message_user(request, _("No entries selected."), messages.WARNING)
        return None
    job = DeletionBatch.objects.create(
        user=request.user, model_name=queryset.model._meta.model_name, object_ids=ids
    )
    return redirect("core:batch-delete", pk=job.pk)


class BatchDelete(View):
    def job(self, request, pk, lock=False):
        if (
            not request.user.is_authenticated
            or not request.user.is_active
            or not request.user.is_staff
        ):
            raise PermissionDenied
        qs = (
            DeletionBatch.objects.select_for_update() if lock else DeletionBatch.objects
        )
        job = get_object_or_404(
            qs,
            pk=pk,
            user=request.user,
            created__gte=timezone.now() - timedelta(days=1),
        )
        from django.apps import apps

        model = apps.get_model("core", job.model_name)
        model_admin = admin.site._registry.get(model)
        if (
            not model_admin
            or job.model_name in EXCLUDED
            or not model_admin.has_delete_permission(request)
        ):
            raise PermissionDenied
        return job, model_admin

    def get(self, request, pk):
        job, model_admin = self.job(request, pk)
        return TemplateResponse(
            request,
            "admin/batch_delete.html",
            {
                **admin.site.each_context(request),
                "title": _("Delete selected entries"),
                "job": job,
                "model_label": model_admin.model._meta.verbose_name_plural,
                "total": len(job.object_ids),
                "back_url": reverse(f"admin:core_{job.model_name}_changelist"),
            },
        )

    def post(self, request, pk):
        try:
            with transaction.atomic():
                job, model_admin = self.job(request, pk, lock=True)
                if request.POST.get("confirm") != "yes":
                    return JsonResponse(
                        {"error": str(_("Confirm the deletion first."))}, status=400
                    )
                try:
                    position = int(request.POST.get("position", ""))
                except ValueError:
                    return JsonResponse(
                        {"error": str(_("Invalid batch position."))}, status=400
                    )
                # A repeated request returns progress without deleting the next batch.
                if position == job.position and job.position < len(job.object_ids):
                    ids = job.object_ids[job.position : job.position + BATCH_SIZE]
                    objects = scoped(
                        model_admin.get_queryset(request), request.user
                    ).filter(pk__in=ids)
                    count = objects.count()
                    related_objects, related_counts, permissions, protected = (
                        model_admin.get_deleted_objects(objects, request)
                    )
                    if permissions or protected:
                        return JsonResponse(
                            {
                                "error": str(
                                    _(
                                        "Deletion stopped: a selected entry has protected data or needs additional permissions."
                                    )
                                )
                            },
                            status=409,
                        )
                    for obj in objects:
                        if not model_admin.has_delete_permission(request, obj):
                            raise PermissionDenied
                    model_admin.log_deletions(request, objects)
                    model_admin.delete_queryset(request, objects)
                    job.position += len(ids)
                    job.deleted += count
                    job.skipped += len(ids) - count
                    job.confirmed = True
                    job.save(
                        update_fields=["position", "deleted", "skipped", "confirmed"]
                    )
                return JsonResponse(
                    {
                        "position": job.position,
                        "deleted": job.deleted,
                        "skipped": job.skipped,
                        "total": len(job.object_ids),
                        "done": job.position == len(job.object_ids),
                    }
                )
        except (ProtectedError, OperationalError):
            return JsonResponse(
                {
                    "error": str(
                        _(
                            "This batch was not deleted. Check for protected entries or another active update, then retry."
                        )
                    )
                },
                status=409,
            )
