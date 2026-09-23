"""Extract, merge, compile, and validate catalogs without platform gettext tools.

Development dependencies: pip install -r scripts/requirements-i18n.txt
This command never sends strings or user data over the network.
"""

import argparse
import io
import json
import re
from pathlib import Path
import polib
from babel.messages.extract import extract, DEFAULT_KEYWORDS
from django.utils.translation import templatize

ROOT = Path(__file__).resolve().parents[1]
APPS = ("babybuddy", "core", "dashboard", "reports", "inventory", "api")
SKIP = {"migrations", "tests", "static", "__pycache__"}


def save_catalog(catalog, path):
    """Replace completed catalogs atomically; never truncate a live catalog."""
    import os
    import tempfile
    import time

    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.stem + "-", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    try:
        catalog.save(temporary)
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(0.2)
    finally:
        Path(temporary).unlink(missing_ok=True)


def messages():
    catalogs = {"django": {}, "djangojs": {}}
    for app in APPS:
        for path in (ROOT / app).rglob("*"):
            if (
                not path.is_file()
                or SKIP.intersection(path.parts)
                or path.name.startswith("test")
            ):
                continue
            domain = "django"
            if path.suffix == ".py":
                method, source = "python", path.read_bytes()
            elif path.suffix == ".html" and "templates" in path.parts:
                method = "python"
                source = "\n".join(
                    line.lstrip()
                    for line in templatize(
                        path.read_text(encoding="utf-8"), origin=str(path)
                    ).splitlines()
                ).encode("utf-8")
            elif path.suffix == ".js" and "static_src" in path.parts:
                method, source, domain = "javascript", path.read_bytes(), "djangojs"
            else:
                continue
            for line, message, comments, context in extract(
                method,
                io.BytesIO(source),
                keywords={**DEFAULT_KEYWORDS, "gettext_noop": None},
                comment_tags=("Translators:",),
            ):
                if not message:
                    continue
                singular, plural = (
                    message if isinstance(message, tuple) else (message, "")
                )
                key = (context, singular, plural)
                entry = catalogs[domain].setdefault(
                    key, {"occurrences": [], "comments": []}
                )
                entry["occurrences"].append(
                    (str(path.relative_to(ROOT)).replace("\\", "/"), str(line))
                )
                entry["comments"].extend(comments)
    return catalogs


def export_messages():
    """Export fixed UI text only for isolated, offline development tools."""
    output = ROOT / "data/interface-messages.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {domain: list(entries) for domain, entries in messages().items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update():
    extracted = messages()
    for domain, entries in extracted.items():
        for folder in sorted((ROOT / "locale").iterdir()):
            path = folder / "LC_MESSAGES" / (domain + ".po")
            if not path.parent.exists():
                continue
            if path.exists():
                catalog = polib.pofile(str(path))
            else:
                catalog = polib.POFile()
                base = polib.pofile(str(path.with_name("django.po")))
                catalog.metadata = dict(base.metadata)
            for (context, singular, plural), item in entries.items():
                entry = catalog.find(singular, msgctxt=context)
                if entry is None:
                    entry = polib.POEntry(
                        msgid=singular, msgid_plural=plural, msgctxt=context
                    )
                    if plural:
                        count = int(
                            re.search(
                                r"nplurals=(\d+)",
                                catalog.metadata.get("Plural-Forms", "nplurals=2;"),
                            ).group(1)
                        )
                        entry.msgstr_plural = {index: "" for index in range(count)}
                    catalog.append(entry)
                entry.occurrences = item["occurrences"]
                entry.comment = "\n".join(dict.fromkeys(item["comments"]))
                entry.obsolete = False
            save_catalog(catalog, path)
        print(domain, len(entries), "active source messages")
    return extracted


def placeholders(value):
    return set(
        re.findall(r"%\([^)]+\)[#0 +\-]*[0-9.]*[a-zA-Z]|\{[a-zA-Z_][\w]*\}", value)
    )


def check(compile_files=False):
    problems, coverage, catalogs = [], {}, []
    extracted = messages()
    for path in sorted((ROOT / "locale").glob("*/LC_MESSAGES/*.po")):
        catalog = polib.pofile(str(path))
        active = extracted[path.stem]
        missing = []
        for context, singular, plural in active:
            entry = catalog.find(singular, msgctxt=context)
            if entry is None or not entry.translated():
                missing.append(singular)
                continue
            allowed = placeholders(singular) | placeholders(plural)
            for target in (
                [entry.msgstr] if not plural else entry.msgstr_plural.values()
            ):
                actual = placeholders(target)
                # Some singular/dual translations spell the count out. They may
                # omit it, but cannot introduce unknown interpolation keys.
                if actual - allowed or (not plural and actual != allowed):
                    problems.append(f"{path}: placeholder mismatch: {singular}")
                if len(re.findall(r"%\([^)]+\)", target)) != len(
                    re.findall(r"%\([^)]+\)[#0 +\-]*[0-9.]*[a-zA-Z]", target)
                ):
                    problems.append(f"{path}: malformed placeholder: {singular}")
        coverage[str(path.relative_to(ROOT))] = {
            "active": len(active),
            "missing": missing,
        }
        catalogs.append((path, catalog))
    output = ROOT / "data" / "localization-coverage.json"
    output.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "Missing active translations:",
        sum(len(row["missing"]) for row in coverage.values()),
    )
    if problems:
        raise SystemExit("\n".join(problems[:30]))
    if compile_files:
        for path, catalog in catalogs:
            catalog.save_as_mofile(str(path.with_suffix(".mo")))
    print("Placeholder validation passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("update", "export", "check", "compile"))
    args = parser.parse_args()
    if args.command == "update":
        update()
    elif args.command == "export":
        export_messages()
    else:
        check(compile_files=args.command == "compile")
