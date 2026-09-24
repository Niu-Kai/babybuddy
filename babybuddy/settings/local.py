"""Loopback-only settings for the guided Windows installation."""

from .development import *

# Serve the prebuilt files included in this fork through WhiteNoise.
DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "::1"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "data", "db.sqlite3"),
    }
}
