# -*- coding: utf-8 -*-
"""
Outgoing webhooks (babybuddy/babybuddy#813).

When the "Webhook URL" site setting is set, every create, update and delete
of an entry is POSTed there as JSON, in a background thread so a slow or
absent receiver never delays the request that caused it. The payload's
`data` is the entry as the API would serialise it.
"""

import hashlib
import hmac
import json
import logging
import threading
import urllib.request

from django.db.models.signals import post_delete, post_save
from django.utils import timezone

logger = logging.getLogger(__name__)

WATCHED_MODELS = (
    "Appointment",
    "BMI",
    "DiaperChange",
    "Feeding",
    "HeadCircumference",
    "Height",
    "Medication",
    "Note",
    "Pumping",
    "Sleep",
    "Temperature",
    "TummyTime",
    "Weight",
)
TIMEOUT_SECONDS = 5


def serialize(instance):
    """The entry as the API would return it; falls back to its id."""
    from api import serializers

    serializer_class = getattr(
        serializers, f"{type(instance).__name__}Serializer", None
    )
    if serializer_class is None:
        return {"id": instance.pk}
    try:
        return json.loads(json.dumps(serializer_class(instance).data, default=str))
    except Exception:  # pragma: no cover - defensive, e.g. deleted relations
        return {"id": instance.pk}


def build_payload(instance, action):
    child = getattr(instance, "child", None)
    return {
        "event": f"{instance._meta.model_name}.{action}",
        "model": instance._meta.model_name,
        "action": action,
        "id": instance.pk,
        "child": (
            {"id": child.pk, "slug": child.slug, "name": str(child)} if child else None
        ),
        "data": {"id": instance.pk} if action == "deleted" else serialize(instance),
        "timestamp": timezone.now().isoformat(),
    }


def send(url, payload, secret=""):
    """POST one payload; failures are logged, never raised."""
    body = json.dumps(payload, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Baby Buddy"}
    if secret:
        headers["X-BabyBuddy-Signature"] = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except Exception as exc:
        logger.warning("Webhook %s failed for %s: %s", url, payload["event"], exc)


def deliver_async(url, payload, secret=""):
    threading.Thread(target=send, args=(url, payload, secret), daemon=True).start()


def dispatch(instance, action):
    from core.models import Child

    url = (Child.webhooks.url or "").strip()
    if not url:
        return
    deliver_async(url, build_payload(instance, action), Child.webhooks.secret or "")


def on_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    dispatch(instance, "created" if created else "updated")


def on_delete(sender, instance, **kwargs):
    dispatch(instance, "deleted")


def connect():
    from core import models

    for name in WATCHED_MODELS:
        model = getattr(models, name)
        post_save.connect(on_save, sender=model, dispatch_uid=f"webhook_save_{name}")
        post_delete.connect(
            on_delete, sender=model, dispatch_uid=f"webhook_delete_{name}"
        )
