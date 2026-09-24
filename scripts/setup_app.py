"""Guided local setup and launcher; never upgrades an existing installation."""

import argparse
from contextlib import contextmanager
import gzip
import getpass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = "babybuddy.settings.local"
STATE_NAME = "local-setup.json"


def python_path(root):
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def read_state(root):
    path = root / "data" / STATE_NAME
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise RuntimeError(
            "Invalid setup state. Keep your data and use the update guide."
        )
    if state.get("version") != 1 or state.get("status") not in ("installing", "ready"):
        raise RuntimeError(
            "Unknown setup state. Keep your data and use the update guide."
        )
    return state


def preflight(root):
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Use Python 3.14 for this installer.")
    required = (
        "manage.py",
        "requirements.lock",
        "static/babybuddy/css/app.css",
        "static/babybuddy/js/app.js",
        "static/babybuddy/js/graph.js",
    )
    for relative in required:
        if not (root / relative).is_file():
            raise RuntimeError(
                f"Missing {relative}. Extract the complete fork ZIP first."
            )
    if (
        (root / ".env").exists()
        or os.environ.get("DATABASE_URL")
        or any(key.startswith("DB_") for key in os.environ)
    ):
        raise RuntimeError(
            "An existing/custom configuration was found. Use docs/setup/updating.md; Setup will not change it."
        )
    state = read_state(root)
    database = root / "data/db.sqlite3"
    if state and state["status"] == "ready" and not database.is_file():
        raise RuntimeError(
            "Your database is missing. Restore it from backup; Setup will not recreate it."
        )
    if not state and database.exists():
        raise RuntimeError(
            "An existing database was found. Use your usual launcher and docs/setup/updating.md; Setup will not replace it."
        )
    return state


def save_state(root, status):
    directory = root / "data"
    directory.mkdir(exist_ok=True)
    temporary = directory / (STATE_NAME + ".tmp")
    temporary.write_text(
        json.dumps({"version": 1, "status": status}) + "\n", encoding="utf-8"
    )
    temporary.replace(directory / STATE_NAME)


@contextmanager
def setup_lock(root):
    directory = root / "data"
    directory.mkdir(exist_ok=True)
    with (directory / "local-setup.lock").open("a+b") as lock:
        lock.seek(0)
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Setup is already running in another window.") from error
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def refresh_assets(root):
    # A source update can leave an older gzip beside a newer uncompressed bundle.
    # WhiteNoise negotiates gzip automatically; ensure both represent the same UI.
    for compressed in (root / "static").rglob("*.gz"):
        source = compressed.with_suffix("")
        if not source.is_file():
            continue
        content = source.read_bytes()
        try:
            current = gzip.decompress(compressed.read_bytes())
        except (OSError, EOFError):
            current = None
        if current != content:
            compressed.write_bytes(gzip.compress(content, mtime=0))


def environment():
    result = os.environ.copy()
    # This installer has fixed local settings; do not load a parent folder's .env.
    result["PYTHON_DOTENV_DISABLED"] = "1"
    result["DJANGO_SETTINGS_MODULE"] = SETTINGS
    result["PYTHONUTF8"] = "1"
    return result


def run(root, command):
    subprocess.run(
        [str(part) for part in command], cwd=root, env=environment(), check=True
    )


def configure_database(root):
    preflight(root)
    if read_state(root) != {"version": 1, "status": "installing"}:
        raise RuntimeError(
            "Run Setup first. Existing installations use the update guide."
        )
    os.environ.update(environment())
    sys.path.insert(0, str(root))
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import (
        validate_password,
        MinimumLengthValidator,
        CommonPasswordValidator,
        NumericPasswordValidator,
        UserAttributeSimilarityValidator,
    )
    from django.core.exceptions import ValidationError
    from django.core.management import call_command
    from django.core.management.commands.migrate import Command as MigrateCommand

    # Bypass the legacy project's migrate override that creates admin/admin.
    call_command(MigrateCommand(), interactive=False)
    User = get_user_model()
    if not User.objects.filter(is_superuser=True, is_active=True).exists():
        print("\nCreate your Baby Buddy account. Your password stays on this computer.")
        while True:
            username = input("Username: ").strip()
            try:
                User._meta.get_field("username").clean(username, None)
                if User.objects.filter(username=username).exists():
                    raise ValidationError(
                        "That username already exists. Choose another."
                    )
                candidate = User(username=username)
                password = getpass.getpass("Password: ")
                validate_password(
                    password,
                    candidate,
                    password_validators=[
                        MinimumLengthValidator(10),
                        CommonPasswordValidator(),
                        NumericPasswordValidator(),
                        UserAttributeSimilarityValidator(),
                    ],
                )
                if password != getpass.getpass("Confirm password: "):
                    raise ValidationError("Passwords do not match.")
            except ValidationError as error:
                print(" ".join(error.messages))
                continue
            User.objects.create_superuser(username=username, password=password)
            break
    call_command("check")
    refresh_assets(root)
    save_state(root, "ready")
    print(
        '\nSetup complete. Double-click "Start Baby Buddy.cmd" whenever you want to use the app.'
    )


def setup(root):
    state = preflight(root)
    if state and state["status"] == "ready":
        print(
            'Already set up. Use "Start Baby Buddy.cmd". For new code, follow docs/setup/updating.md.'
        )
        return
    if not state:
        save_state(root, "installing")
    runtime = python_path(root)
    if not runtime.exists():
        print("[1/3] Creating a private Python environment...")
        run(root, [sys.executable, "-m", "venv", root / ".venv"])
    run(
        root,
        [
            runtime,
            "-c",
            "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)",
        ],
    )
    print(
        "[2/3] Installing verified dependencies (internet required on first setup)..."
    )
    run(
        root,
        [
            runtime,
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "-r",
            "requirements.lock",
        ],
    )
    run(root, [runtime, "-m", "pip", "check"])
    print("[3/3] Preparing your database and account...")
    run(root, [runtime, root / "scripts/setup_app.py", "configure"])


def available_port(first):
    for port in range(first, min(first + 20, 65536)):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(
        "No free local port found. Close another copy of Baby Buddy and try again."
    )


def start(root, port=8000, open_browser=True):
    preflight(root)
    if not read_state(root) or read_state(root)["status"] != "ready":
        raise RuntimeError(
            'Run "Setup Baby Buddy.cmd" first and finish creating your account.'
        )
    if not (root / "data/db.sqlite3").is_file():
        raise RuntimeError(
            "Your database is missing. Restore it from backup; Setup will not recreate it."
        )
    port = available_port(port)
    url = f"http://127.0.0.1:{port}/"
    run(root, [python_path(root), root / "scripts/setup_app.py", "verify"])
    refresh_assets(root)
    process = subprocess.Popen(
        [
            str(python_path(root)),
            "manage.py",
            "runserver",
            f"127.0.0.1:{port}",
            "--noreload",
            "--nostatic",
        ],
        cwd=root,
        env=environment(),
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("The server could not start. See the error above.")
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise RuntimeError(
                "The server did not become ready. See the error above and try Start again."
            )
        print(
            f"\nBaby Buddy is ready: {url}\nKeep this window open. Press Ctrl+C to stop.",
            flush=True,
        )
        if open_browser:
            webbrowser.open(url)
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def verify_database(root):
    preflight(root)
    if not read_state(root) or read_state(root)["status"] != "ready":
        raise RuntimeError("Finish Setup before starting the app.")
    os.environ.update(environment())
    sys.path.insert(0, str(root))
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    call_command("check")
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise RuntimeError(
            "Database updates are needed. Stop the app and follow docs/setup/updating.md."
        )
    if not get_user_model().objects.filter(is_superuser=True, is_active=True).exists():
        raise RuntimeError(
            "No active administrator exists. Recover your account before starting the app."
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("setup", "configure", "start", "check", "verify")
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    try:
        if args.action == "setup":
            preflight(ROOT)
            with setup_lock(ROOT):
                setup(ROOT)
        elif args.action == "configure":
            configure_database(ROOT)
        elif args.action == "verify":
            verify_database(ROOT)
        elif args.action == "start":
            start(ROOT, args.port, not args.no_browser)
        else:
            preflight(ROOT)
            print("Prerequisites OK. No files or database records changed.")
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(
            f"\nStopped: {error}\nKeep this folder. Fix the reported problem and run the same launcher again.",
            file=sys.stderr,
        )
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Your data is kept. Run the launcher again when ready.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
