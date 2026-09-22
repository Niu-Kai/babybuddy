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
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import urllib.request

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

logger = logging.getLogger(__name__)

WATCHED_MODELS = (
    "Appointment",
    "BathTime",
    "BMI",
    "Food",
    "Reflux",
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
MAX_PENDING = 64
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="babybuddy-webhook")
_pending = threading.BoundedSemaphore(MAX_PENDING)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Payloads and signatures must only reach the configured receiver.
        return None


_opener = urllib.request.build_opener(NoRedirect())


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
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(ord(char) < 32 or ord(char) == 127 for char in url)
        ):
            raise ValueError("Invalid webhook destination")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with _opener.open(request, timeout=TIMEOUT_SECONDS):
            pass
    except Exception as exc:
        # Webhook URLs often contain credentials. Neither URLs nor exception
        # messages (which may repeat URLs) belong in application logs.
        logger.warning(
            "Webhook delivery failed for %s (%s)", payload["event"], type(exc).__name__
        )


def deliver_async(url, payload, secret=""):
    if not _pending.acquire(blocking=False):
        logger.warning("Webhook queue full; event %s was not queued", payload["event"])
        return
    try:
        future = _executor.submit(send, url, payload, secret)
    except Exception as exc:
        _pending.release()
        logger.warning("Webhook could not be queued (%s)", type(exc).__name__)
        return
    future.add_done_callback(lambda completed: _pending.release())


def dispatch(instance, action, using="default"):
    from core.models import Child

    url = (Child.webhooks.url or "").strip()
    if not url:
        return
    payload = build_payload(instance, action)
    secret = Child.webhooks.secret or ""
    transaction.on_commit(
        lambda: deliver_async(url, payload, secret), using=using, robust=True
    )


def on_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    dispatch(
        instance, "created" if created else "updated", kwargs.get("using", "default")
    )


def on_delete(sender, instance, **kwargs):
    dispatch(instance, "deleted", kwargs.get("using", "default"))


def connect():
    from core import models

    for name in WATCHED_MODELS:
        model = getattr(models, name)
        post_save.connect(on_save, sender=model, dispatch_uid=f"webhook_save_{name}")
        post_delete.connect(
            on_delete, sender=model, dispatch_uid=f"webhook_delete_{name}"
        )
