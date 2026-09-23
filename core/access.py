"""Request-scoped child access, independent of the visible child selector.

Background jobs remain unscoped. API viewsets also scope their class-level querysets.
"""

from contextvars import ContextVar
from contextlib import contextmanager
from django.db import models

_request = ContextVar("child_access_request", default=None)


def restricted(user):
    return bool(
        user
        and user.is_authenticated
        and not user.is_superuser
        and user.settings.restrict_children
    )


def child_ids(user):
    if not restricted(user):
        return None
    if not hasattr(user, "_allowed_child_ids"):
        through = user.settings.allowed_children.through
        user._allowed_child_ids = tuple(
            through.objects.filter(settings_id=user.settings.pk).values_list(
                "child_id", flat=True
            )
        )
    return user._allowed_child_ids


def can_access(user, child_id):
    ids = child_ids(user)
    return ids is None or (child_id is not None and child_id in ids)


def scoped(queryset, user):
    ids = child_ids(user)
    if ids is None:
        return queryset
    model = queryset.model
    if model._meta.label_lower == "core.child":
        return queryset.filter(pk__in=ids)
    if model._meta.model_name == "pumping":
        return queryset
    if any(f.name == "child" for f in model._meta.fields):
        condition = models.Q(child_id__in=ids)
        if model._meta.model_name == "timer":
            condition |= models.Q(child__isnull=True)
        return queryset.filter(condition)
    return queryset


class ChildAccessManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        request = _request.get()
        return scoped(queryset, request.user) if request else queryset


@contextmanager
def unscoped():
    token = _request.set(None)
    try:
        yield
    finally:
        _request.reset(token)


class ChildAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)
