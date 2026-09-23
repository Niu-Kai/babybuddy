"""Explicit local SQLite update helper. Default: check prerequisites only."""

from contextlib import closing
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def backup(destination, database, media, source_files):
    destination.mkdir(parents=True, exist_ok=False)
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as source, closing(sqlite3.connect(destination / "db.sqlite3")) as copy:
        source.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed.")
    with zipfile.ZipFile(
        destination / "files.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for relative in source_files:
            path = ROOT / relative
            if (
                path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(ROOT)
            ):
                archive.write(path, "source/" + relative.replace(os.sep, "/"))
        if media.exists():
            for path in media.rglob("*"):
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.resolve().is_relative_to(media)
                ):
                    archive.write(path, "media/" + path.relative_to(media).as_posix())
        for relative in (".env", ".development-secret-key"):
            path = ROOT / relative
            if path.is_file() and not path.is_symlink():
                archive.write(path, "private/" + relative)
    with zipfile.ZipFile(destination / "files.zip") as archive:
        if archive.testzip() is not None:
            raise RuntimeError("File backup integrity check failed.")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--server-stopped", action="store_true")
    parser.add_argument("--skip-dependencies", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "data" / "backups")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = args.settings
    import django

    django.setup()
    from django.conf import settings
    from django.core.files.storage import default_storage, FileSystemStorage

    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
        parser.error(
            "This helper backs up SQLite only. Follow docs/setup/updating.md for PostgreSQL."
        )
    if not isinstance(default_storage, FileSystemStorage):
        parser.error(
            "This helper supports local media only. Back up remote media with its provider."
        )
    database = Path(settings.DATABASES["default"]["NAME"]).resolve()
    media = Path(default_storage.location).resolve()
    if not database.is_file():
        parser.error("Existing SQLite database not found.")
    backup_root = args.backup_dir.resolve()
    if backup_root == media or backup_root.is_relative_to(media):
        parser.error("Backup directory must be outside the media directory.")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which("node")
    if not npm or not node or not shutil.which("git"):
        parser.error("Install Node.js, npm, and Git first.")
    run([node, "--version"])
    run([sys.executable, "manage.py", "check", "--settings=" + args.settings])
    run(
        [
            sys.executable,
            "manage.py",
            "migrate",
            "--plan",
            "--settings=" + args.settings,
        ]
    )
    if not args.apply:
        print(
            "Checks complete. Nothing changed. Stop the server, then use --apply --server-stopped."
        )
        return 0
    if not args.server_stopped:
        parser.error("Stop the server and workers, then pass --server-stopped.")
    snapshot = (
        run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    folder = backup_root / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    backup(folder, database, media, [name for name in snapshot if name])
    head = run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "commit": head,
                "settings": args.settings,
                "database": str(database),
                "media": str(media),
                "python": sys.version,
                "source_includes_working_changes": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Verified backup:", folder)
    try:
        if not args.skip_dependencies:
            run([sys.executable, "-m", "pip", "install", "-r", "requirements.lock"])
            run([npm, "ci"])
        run([sys.executable, "scripts/lock_requirements.py"])
        run([sys.executable, "-m", "pip", "check"])
        run([node, ROOT / "node_modules/gulp/bin/gulp.js", "build"])
        run([sys.executable, "manage.py", "check", "--settings=" + args.settings])
        run(
            [
                sys.executable,
                "manage.py",
                "migrate",
                "--noinput",
                "--settings=" + args.settings,
            ]
        )
        run(
            [
                sys.executable,
                "manage.py",
                "collectstatic",
                "--noinput",
                "--settings=" + args.settings,
            ]
        )
        run([sys.executable, "manage.py", "check", "--settings=" + args.settings])
    except subprocess.CalledProcessError:
        print(
            "Update stopped. Keep the server stopped. Recovery backup:",
            folder,
            file=sys.stderr,
        )
        print(
            "Follow docs/setup/updating.md. No automatic rollback was attempted.",
            file=sys.stderr,
        )
        return 1
    print("Update finished. Start the server and verify login, a report, and a photo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
