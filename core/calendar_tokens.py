"""Read-only, child-scoped calendar credentials; never share a general API key."""

import re
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.authtoken.models import Token
from babybuddy.models import access_expired


def feed_token(user, child):
    key, _ = Token.objects.get_or_create(user=user)
    return _token(user.pk, child.pk, key.key)


def _token(user_id, child_id, key):
    digest = salted_hmac(
        "babybuddy.calendar-feed.v1",
        f"{user_id}:{child_id}",
        secret=f"{settings.SECRET_KEY}:{key}",
        algorithm="sha256",
    ).hexdigest()
    return f"{user_id}-{digest}"


def feed_user(value, child):
    match = re.fullmatch(r"([0-9]{1,18})-([a-f0-9]{64})", value)
    if not match:
        return None
    user = get_user_model().objects.filter(pk=int(match[1]), is_active=True).first()
    if not user or access_expired(user) or not user.has_perm("core.view_appointment"):
        return None
    from core.access import can_access

    if not can_access(user, child.pk):
        return None
    key = Token.objects.filter(user=user).first()
    if key and constant_time_compare(value, _token(user.pk, child.pk, key.key)):
        return user
    return None
