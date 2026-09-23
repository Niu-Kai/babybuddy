"""One-time development tool; never imported by the running application.

Sends only extracted English UI text to Google's public translation endpoint.
Requires explicit --google-interface-text authorization. Existing active,
non-fuzzy translations are preserved. New translations are reviewable drafts.
No application settings, database records, or credentials are read.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gettext
import json
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polib
from localization import ROOT, messages, placeholders

ALIASES = {
    "Caregiver fed": "Fed by a caregiver",
    "Pumping": "Breast milk pumping",
    "Last pumping": "Last breast milk pumping",
    "Left": "Left side",
    "Right": "Right side",
    "Both": "Both sides",
    "Formula": "Infant formula",
    "%(counter)s pumping": "%(counter)s breast milk pumping session",
    "%(counter)s pumpings": "%(counter)s breast milk pumping sessions",
}
LANGUAGES = {
    "zh_Hans": "zh-CN",
    "zh_Hant": "zh-TW",
    "zh_TW": "zh-TW",
    "pt_BR": "pt",
    "pt": "pt-PT",
    "nb": "no",
}
TOKENS = re.compile(r"%\([^)]+\)[#0 +\-]*[0-9.]*[a-zA-Z]|<[^>]+>|&[A-Za-z#0-9]+;|\n")
DRAFT = "Machine-assisted Google draft; fluent-speaker review required."
LOCK = threading.Lock()
LAST_REQUEST = 0.0
PROVIDER_STOP = threading.Event()


def request_translation(text, language):
    global LAST_REQUEST
    if PROVIDER_STOP.is_set():
        raise RuntimeError("Provider requests stopped after a denial or rate limit")
    with LOCK:
        if PROVIDER_STOP.is_set():
            raise RuntimeError("Provider requests stopped after a denial or rate limit")
        time.sleep(max(0, 0.7 - (time.monotonic() - LAST_REQUEST)))
        LAST_REQUEST = time.monotonic()
    query = urlencode(
        {"client": "gtx", "sl": "en", "tl": language, "dt": "t", "q": text}
    )
    request = Request(
        "https://translate.googleapis.com/translate_a/single?" + query,
        headers={"User-Agent": "BabyBuddy-interface-localization/1.0"},
    )
    # No retry of denials or rate limits, no paid API or account credentials.
    try:
        with urlopen(request, timeout=35) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code in (403, 429):
            PROVIDER_STOP.set()
        delay = error.headers.get("Retry-After", "not provided")
        raise RuntimeError(
            f"Google returned HTTP {error.code}; Retry-After: {delay}"
        ) from error
    return "".join(part[0] or "" for part in data[0])


def protect(source):
    tokens = []

    def replace(match):
        tokens.append(match.group())
        return "ZXPH" + str(len(tokens) - 1) + "XZ"

    return TOKENS.sub(replace, source), tokens


def restore(target, tokens):
    for index, token in enumerate(tokens):
        marker = f"ZXPH{index}XZ"
        # Some languages insert whitespace around a token's digit.
        pattern = rf"ZXPH\s*{index}\s*XZ"
        if len(re.findall(pattern, target, re.I)) != 1:
            raise ValueError("Response changed an interpolation/markup token")
        target = re.sub(pattern, lambda _: token, target, flags=re.I)
    if "ZXPH" in target or not target.strip():
        raise ValueError("Invalid translation token or empty translation")
    return target.strip()


def translate_batch(sources, language):
    protected = [protect(source) for source in sources]
    query = "\n".join(f"[[BB{i:04d}]] {text}" for i, (text, _) in enumerate(protected))
    translated = request_translation(query, language)
    matches = list(re.finditer(r"\[\[BB\s*(\d{4})\]\]", translated))
    if len(matches) != len(sources) or [int(m[1]) for m in matches] != list(
        range(len(sources))
    ):
        # A smaller request solves formatting loss, never provider denials.
        return [
            restore(request_translation(text, language), tokens)
            for text, tokens in protected
        ]
    results = []
    for index, match in enumerate(matches):
        target = translated[
            match.end() : (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(translated)
            )
        ]
        try:
            results.append(restore(target, protected[index][1]))
        except ValueError:
            results.append(
                restore(
                    request_translation(protected[index][0], language),
                    protected[index][1],
                )
            )
    return results


def plural_samples(catalog):
    metadata = catalog.metadata["Plural-Forms"]
    count = int(re.search(r"nplurals\s*=\s*(\d+)", metadata)[1])
    expression = re.search(r"plural\s*=\s*(.*?);", metadata)[1]
    function = gettext.c2py(expression)
    result = {}
    # Prefer 1 for singular, 2/5 for plural; avoid translating zero as absence.
    for value in [1, 2, 5, 3, 4, 11, 21, 101, *range(6, 201), 0]:
        result.setdefault(function(value), value)
    # Some inherited catalogs reserve a fractional slot, unused by integer counts.
    return [result.get(index, 1.5) for index in range(count)]


def plural_request(singular, plural, sample):
    source = singular if sample == 1 else plural
    source = ALIASES.get(source, source)
    found = sorted(placeholders(singular) | placeholders(plural))
    if found:
        if len(found) != 1:
            raise ValueError("Plural message requires explicit count review")
        token = found[0]
        if token not in source:
            # The existing tag-count singular spells out a literal 1.
            source = source.replace("1", token, 1)
        return source.replace(token, str(sample)), token
    # Give the translator a numeric context, then keep only the inflected noun.
    return f"{sample} {source}", ""


def restore_count(value, sample, token):
    number = str(sample).replace(".", "[.,]")
    pattern = rf"(?<![\d]){number}(?![\d])"
    if len(re.findall(pattern, value)) != 1:
        raise ValueError(f"Plural count was not preserved for example {sample}")
    return re.sub(pattern, lambda _: token, value, count=1).strip()


def validate(source, target, plural=""):
    allowed = placeholders(source) | placeholders(plural)
    if placeholders(target) - allowed or (
        not plural and placeholders(target) != allowed
    ):
        raise ValueError("Placeholder mismatch")
    # Only source markup may appear in compiled interface messages.
    if re.findall(r"<[^>]+>", target) != re.findall(r"<[^>]+>", source):
        raise ValueError("Markup changed")


def run(language, active):
    folder = ROOT / "locale" / language / "LC_MESSAGES"
    if not folder.is_dir():
        raise ValueError("Unknown existing locale")
    catalogs, jobs = [], []
    for domain, sources in active.items():
        path = folder / (domain + ".po")
        catalog = polib.pofile(str(path))
        samples = plural_samples(catalog)
        for context, singular, plural in sources:
            entry = catalog.find(singular, msgctxt=context)
            if entry is None:
                raise ValueError("Run localization.py update first")
            fuzzy = "fuzzy" in entry.flags
            if plural:
                for index, sample in enumerate(samples):
                    if fuzzy or not entry.msgstr_plural.get(index):
                        phrase, token = plural_request(singular, plural, sample)
                        jobs.append((entry, index, phrase, sample, token))
            elif fuzzy or not entry.msgstr:
                jobs.append((entry, None, ALIASES.get(singular, singular), None, None))
        catalogs.append((path, catalog))
    cache_path = ROOT / "data" / f"translation-drafts-{language}.json"
    cache = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    pending = sorted({job[2] for job in jobs} - cache.keys())
    if language == "en_GB":
        cache.update({phrase: phrase for phrase in pending})
    else:
        batches, batch, size = [], [], 0
        for phrase in pending:
            length = len(protect(phrase)[0]) + 20
            if batch and size + length > 1700:
                batches.append(batch)
                batch, size = [], 0
            batch.append(phrase)
            size += length
        if batch:
            batches.append(batch)
        for index, batch in enumerate(batches):
            values = translate_batch(batch, LANGUAGES.get(language, language))
            cache.update(zip(batch, values))
            cache_path.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(language, f"batch {index + 1}/{len(batches)}", flush=True)
    prepared = []
    for entry, index, phrase, sample, token in jobs:
        if language == "en_GB":
            target = entry.msgid if index in (None, 0) else entry.msgid_plural
            validate(entry.msgid, target, entry.msgid_plural)
            prepared.append((entry, index, target))
            continue
        target = cache[phrase]
        if index is not None:
            target = restore_count(target, sample, token)
        validate(entry.msgid, target, entry.msgid_plural)
        prepared.append((entry, index, target))
    original_dir = ROOT / "data" / "translation-originals" / language
    original_dir.mkdir(parents=True, exist_ok=True)
    for path, catalog in catalogs:
        original = original_dir / path.name
        if not original.exists():
            original.write_bytes(path.read_bytes())
    recorded = set()
    for entry, index, target in prepared:
        if id(entry) not in recorded:
            if "fuzzy" in entry.flags:
                # Fuzzy translations were not active. Keep their text for review.
                previous = entry.msgstr_plural if entry.msgid_plural else entry.msgstr
                entry.tcomment = (
                    entry.tcomment
                    + "\nPrevious inactive fuzzy translation: "
                    + json.dumps(previous, ensure_ascii=False)
                ).strip()
                entry.flags.remove("fuzzy")
            note = (
                "English source fallback; existing reviewed UK wording retained."
                if language == "en_GB"
                else DRAFT
            )
            entry.tcomment = (entry.tcomment + "\n" + note).strip()
            recorded.add(id(entry))
        if index is None:
            entry.msgstr = target
        else:
            entry.msgstr_plural[index] = target
    for path, catalog in catalogs:
        catalog.save(str(path))
    print(language, f"saved {len(prepared)} translation forms", flush=True)
    return language


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "languages", nargs="+", help="Existing locale directories, or all"
    )
    parser.add_argument(
        "--google-interface-text",
        action="store_true",
        help="Confirm authorization to send interface text to Google",
    )
    args = parser.parse_args()
    if not args.google_interface_text:
        parser.error("Explicit Google interface-text authorization is required")
    languages = (
        sorted(
            p.name
            for p in (ROOT / "locale").iterdir()
            if (p / "LC_MESSAGES/django.po").exists()
        )
        if args.languages == ["all"]
        else args.languages
    )
    active = messages()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            language: executor.submit(run, language, active) for language in languages
        }
        errors = []
        for language, future in futures.items():
            try:
                future.result()
            except Exception as error:
                errors.append(language)
                print(language, type(error).__name__, str(error), flush=True)
        if errors:
            raise SystemExit("Incomplete locales: " + ", ".join(errors))


if __name__ == "__main__":
    main()
