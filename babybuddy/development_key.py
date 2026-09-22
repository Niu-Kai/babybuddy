"""A persistent, private signing key for local development installations."""

import os
import secrets
from pathlib import Path


def local_secret_key(base_dir):
    path = Path(base_dir) / ".development-secret-key"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        value = path.read_text(encoding="utf-8").strip()
    else:
        value = secrets.token_urlsafe(64)
        with os.fdopen(descriptor, "w", encoding="utf-8") as key_file:
            key_file.write(value)
    if len(value) < 50:
        raise ValueError("The local development signing key is invalid.")
    return value
