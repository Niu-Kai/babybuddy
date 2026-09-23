"""Development-only offline catalog drafting and review. Never reads app records.

The draft command writes a local cache, not live catalogs. Apply validates every
form before saving. Existing non-fuzzy translations are never overwritten.
Model files and translation dependencies are intentionally not application deps.
"""

import argparse
import gettext
import json
import os
from pathlib import Path
import re
import sys

import polib

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = dict(
    zip(
        "ca cs da de es fi fr he hr hu it ja ko nb nl pl pt pt_BR ru sr sv tr uk zh_Hans zh_Hant zh_TW".split(),
        "cat_Latn ces_Latn dan_Latn deu_Latn spa_Latn fin_Latn fra_Latn heb_Hebr hrv_Latn hun_Latn ita_Latn jpn_Jpan kor_Hang nob_Latn nld_Latn pol_Latn por_Latn por_Latn rus_Cyrl srp_Cyrl swe_Latn tur_Latn ukr_Cyrl zho_Hans zho_Hant zho_Hant".split(),
    )
)
TOKENS = re.compile(
    r"%\([^)]+\)[#0 +\-]*[0-9.]*[a-zA-Z]|\{[a-zA-Z_][\w]*\}|<[^>]+>|&[A-Za-z#0-9]+;|\n"
)
PLACEHOLDERS = re.compile(r"%\([^)]+\)[#0 +\-]*[0-9.]*[a-zA-Z]|\{[a-zA-Z_][\w]*\}")
DRAFT = "Offline machine-assisted draft; contextual review, not certified translation."
ALIASES = {
    "Top-up bottle": "Supplemental bottle feeding",
    "Add a top-up bottle": "Add a supplemental bottle feeding",
    "Top-up amount": "Supplemental milk volume",
    "Top-up milk type": "Type of supplemental milk",
    "Top-up second milk type": "Second type of supplemental milk",
    "Top-up second amount": "Volume of the second supplemental milk type",
    "Bottle date": "Date of bottle feeding",
    "Bottle time": "Time of bottle feeding",
    "Feeding session": "Baby feeding session",
    "Milk type": "Type of milk for the baby",
    "Group by": "Group the chart by",
    "Enter the top-up bottle amount.": "Enter the volume of milk in the supplemental bottle.",
    "Enter the second milk amount.": "Enter the volume of the second type of milk.",
    "Choose a different second milk type.": "Choose a different milk type for the second part of the bottle.",
    "Choose the top-up milk type.": "Choose the type of milk in the supplemental bottle.",
    "Choose the top-up bottle date and time.": "Choose the date and time of the supplemental bottle feeding.",
    "The top-up bottle cannot start before nursing ends.": "The supplemental bottle feeding cannot start before breastfeeding ends.",
    "A top-up bottle must be linked to a nursing session.": "A supplemental bottle feeding must be linked to a breastfeeding session.",
    "Breastfeeding requires breast milk. Use the top-up bottle fields for a bottle supplement.": "Breastfeeding requires breast milk. Record supplemental bottle feeding using the supplemental bottle fields.",
    "%(child)s had a top-up bottle.": "%(child)s had a supplemental bottle feeding.",
    "Caregiver fed": "Fed by a caregiver",
    "Pumping": "Pumping breast milk",
    "Last Pumping": "Last breast milk pumping session",
    "Last pumping": "Last breast milk pumping session",
    "Recent Pumpings": "Recent breast milk pumping sessions",
    "Pumping & nursing": "Pumping breast milk and breastfeeding",
    "Nursing": "Breastfeeding",
    "Last nursing": "Last breastfeeding session",
    "Pumped today": "Breast milk pumped today",
    "Left breast amount": "Amount of milk pumped from the left breast",
    "Right breast amount": "Amount of milk pumped from the right breast",
    "Formula": "Infant formula",
    "Left": "Left side",
    "Right": "Right side",
    "Both": "Both sides",
    "Entry unit": "Unit used to enter the measurement",
    "Display units": "Units used to display measurements",
    "Tummy time": "Baby tummy time",
    "Tummy Time": "Baby tummy time",
    "Stock unit": "Inventory quantity unit",
    "Running low": "Low stock",
    "Outgrown": "Too small for the child",
    "On hand": "In stock",
    "Correct count": "Correct the stock quantity",
    "Solid only": "Stool only",
    "Wet only": "Urine only",
    "Wet + solid": "Urine and stool",
    "%(counter)s pumping": "%(counter)s breast milk pumping session",
    "%(counter)s pumpings": "%(counter)s breast milk pumping sessions",
    "About %(days)s day left": "Stock remaining for about %(days)s day",
    "About %(days)s days left": "Stock remaining for about %(days)s days",
    "Next dose ready": "Next medication dose is due",
    "Log pumping": "Record a breast milk pumping session",
    "Log nursing": "Record a breastfeeding session",
    "Log activity": "Record an activity",
    "Offline log": "Offline care records",
    "Offline log · Baby Buddy": "Offline care records - Baby Buddy",
    "Pumping or nursing": "Breast milk pumping or breastfeeding",
    "Pumping only": "Breast milk pumping only",
    "Pumping & nursing reminder": "Reminder for breast milk pumping and breastfeeding",
    "Last pumping or nursing session": "Last breast milk pumping or breastfeeding session",
    "Last pumping session": "Last breast milk pumping session",
    "Pumping amount": "Amount of breast milk pumped",
    "Pumped milk": "Expressed breast milk",
    "Pumped amounts": "Amounts of breast milk pumped",
    "Edit pumping entries": "Edit breast milk pumping records",
    "Save pumping": "Save breast milk pumping record",
    "Add a Pumping Entry": "Add a breast milk pumping record",
    "Add Pumping Entry": "Add a breast milk pumping record",
    "Delete a Pumping Entry": "Delete a breast milk pumping record",
    "Pumping · left": "Milk pumped from the left breast",
    "Pumping · right": "Milk pumped from the right breast",
    "Pumping · both": "Milk pumped from both breasts",
    "Pumping · side not recorded": "Milk pumped - breast side not recorded",
    "Nursing · left": "Breastfeeding from the left breast",
    "Nursing · right": "Breastfeeding from the right breast",
    "Nursing · both": "Breastfeeding from both breasts",
    "Daily pumping and nursing comparison": "Daily comparison of breast milk pumping and breastfeeding",
    "All children — combined": "All children together",
    "All children — side by side": "All children side by side",
    "All children · side by side": "All children side by side",
    "Automatic — matching size or age range": "Automatic selection by matching size or age range",
    "Unit not recorded — choose to confirm": "Unit not recorded: select the original unit",
    "Equipment &amp; limits": "Equipment &amp; usage limits",
    "%(child)s's %(medication)s dose wore off.": "%(child)s: dose interval elapsed for %(medication)s.",
    "Update stock · %(name)s": "Update the stock quantity for %(name)s",
    "%(since)s since previous feeding": "Time since previous feeding: %(since)s",
    "The path <code>%(request_path)s</code> does not exist.": "Path not found: <code>%(request_path)s</code>",
    "Use a caregiver or read-only account without staff access for child restrictions.": "To restrict access to selected children, use a caregiver or read-only account. Do not grant staff access to that account.",
}


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def samples(catalog):
    metadata = catalog.metadata["Plural-Forms"]
    count = int(re.search(r"nplurals\s*=\s*(\d+)", metadata)[1])
    function = gettext.c2py(re.search(r"plural\s*=\s*(.*?);", metadata)[1])
    values = {}
    for number in [1, 2, 5, 3, 4, 11, 21, 101, *range(6, 201), 0]:
        values.setdefault(function(number), number)
    return [values.get(index, 1.5) for index in range(count)]


def jobs(language):
    active = read_json(ROOT / "data/interface-messages.json")
    catalogs, pending = [], []
    for domain, messages in active.items():
        path = ROOT / "locale" / language / "LC_MESSAGES" / (domain + ".po")
        catalog = polib.pofile(str(path))
        for context, singular, plural in messages:
            entry = catalog.find(singular, msgctxt=context)
            if entry is None:
                raise ValueError("Run localization.py update before drafting")
            fuzzy = "fuzzy" in entry.flags
            if plural:
                for index, number in enumerate(samples(catalog)):
                    if not fuzzy and entry.msgstr_plural.get(index):
                        continue
                    source = singular if number == 1 else plural
                    phrase = ALIASES.get(source, source)
                    found = set(PLACEHOLDERS.findall(singular + plural))
                    if len(found) > 1:
                        raise ValueError("Plural needs manual count mapping")
                    token = next(iter(found), "")
                    if token:
                        if token not in phrase:
                            phrase = phrase.replace("1", token, 1)
                        phrase = phrase.replace(token, str(number))
                    else:
                        phrase = f"{number} {phrase}"
                    pending.append((entry, index, phrase, number, token))
            elif fuzzy or not entry.msgstr:
                pending.append(
                    (entry, None, ALIASES.get(singular, singular), None, None)
                )
        catalogs.append((path, catalog))
    return catalogs, pending


def protect(source):
    tokens = []

    def replace(match):
        marker = str(812310 + len(tokens))
        if marker in source:
            raise ValueError("Marker collides with source text")
        tokens.append((marker, match.group()))
        return marker

    return TOKENS.sub(replace, source), tokens


def restore(target, tokens):
    if "<unk>" in target or "⁇" in target or "�" in target:
        raise ValueError("Unknown character in draft")
    for marker, original in tokens:
        pattern = r"[\s,.]*".join(marker)
        if len(re.findall(pattern, target)) != 1:
            raise ValueError("Placeholder lost or duplicated")
        target = re.sub(pattern, lambda _: original, target, count=1)
    if not target.strip():
        raise ValueError("Empty translation")
    return target.strip()


def load_model(folder):
    # Windows native loaders may require PATH rather than add_dll_directory.
    bins = [
        str(p.resolve())
        for p in Path(sys.prefix, "Lib/site-packages/nvidia").glob("*/bin")
    ]
    os.environ["PATH"] = os.pathsep.join(bins) + os.pathsep + os.environ["PATH"]
    import ctranslate2
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    model = ctranslate2.Translator(
        str(folder), device="cuda", compute_type="int8_float16"
    )
    return model, tokenizer


def translate_raw(model, tokenizer, sources, language, source_language="eng_Latn"):
    encoded = [
        [source_language]
        + tokenizer.encode(s, add_special_tokens=False).tokens
        + ["</s>"]
        for s in sources
    ]
    results = model.translate_batch(
        encoded,
        target_prefix=[[language]] * len(sources),
        beam_size=4,
        disable_unk=True,
        max_decoding_length=384,
        max_batch_size=32,
    )
    values = []
    for result in results:
        tokens = result.hypotheses[0][1:]
        if "<unk>" in tokens:
            values.append("<unk>")
        else:
            values.append(
                tokenizer.decode(
                    [tokenizer.token_to_id(t) for t in tokens], skip_special_tokens=True
                )
            )
    return values


def translate(model, tokenizer, sources, language, source_language="eng_Latn"):
    # Long multi-sentence inputs can silently lose a sentence in NLLB output.
    # Translate each complete sentence independently and retain their order.
    groups = [re.split(r"(?<=[.!?])\s+(?=[A-Z])", source) for source in sources]
    flat = [sentence for group in groups for sentence in group]
    values = iter(translate_raw(model, tokenizer, flat, language, source_language))
    return [" ".join(next(values) for _ in group) for group in groups]


def draft(language, model, tokenizer):
    _, pending = jobs(language)
    path = ROOT / "data" / f"local-translation-{language}.json"
    cache = read_json(path, {})
    phrases = sorted({row[2] for row in pending} - cache.keys())
    problems = []
    for start in range(0, len(phrases), 32):
        batch = phrases[start : start + 32]
        protected = [protect(phrase) for phrase in batch]
        results = translate(
            model, tokenizer, [p[0] for p in protected], LANGUAGES[language]
        )
        for source, result, (_, tokens) in zip(batch, results, protected):
            try:
                cache[source] = restore(result, tokens)
            except ValueError as error:
                problems.append(
                    {"source": source, "draft": result, "error": str(error)}
                )
        save_json(path, cache)
        print(
            language,
            min(start + 32, len(phrases)),
            "/",
            len(phrases),
            "issues",
            len(problems),
            flush=True,
        )
    save_json(ROOT / "data" / f"local-translation-problems-{language}.json", problems)


def validate(entry, target):
    allowed = set(PLACEHOLDERS.findall(entry.msgid + entry.msgid_plural))
    actual = set(PLACEHOLDERS.findall(target))
    if actual - allowed or (not entry.msgid_plural and actual != allowed):
        raise ValueError("Placeholder mismatch")
    if re.findall(r"<[^>]+>", target) != re.findall(r"<[^>]+>", entry.msgid):
        raise ValueError("Markup mismatch")
    if any(token in target for token in ("<unk>", "⁇", "�")) or not target.strip():
        raise ValueError("Invalid draft characters")


def apply(language, dry_run=False):
    catalogs, pending = jobs(language)
    cache = read_json(ROOT / "data" / f"local-translation-{language}.json", {})
    overrides = read_json(ROOT / "scripts/translation_overrides.json", {}).get(
        language, {}
    )
    prepared, failures = [], []
    for entry, index, phrase, sample, token in pending:
        try:
            key = entry.msgid if index is None else entry.msgid + "|" + str(index)
            target = overrides.get(key)
            if target is None:
                target = cache[phrase]
                if index is not None:
                    pattern = (
                        r"(?<![0-9])"
                        + re.escape(str(sample)).replace(r"\.", "[.,]")
                        + r"(?![0-9])"
                    )
                    if len(re.findall(pattern, target)) != 1:
                        raise ValueError("Plural count was not preserved")
                    target = re.sub(pattern, lambda _: token, target, count=1).strip()
            # Preserve meaningful spacing in short JavaScript fragments.
            if entry.msgid.startswith(" ") and not target.startswith(" "):
                target = " " + target
            if entry.msgid.endswith(" ") and not target.endswith(" "):
                target += " "
            validate(entry, target)
            prepared.append((entry, index, target))
        except (ValueError, KeyError) as error:
            failures.append(
                {
                    "source": entry.msgid,
                    "index": index,
                    "phrase": phrase,
                    "error": str(error),
                }
            )
    save_json(ROOT / "data" / f"local-translation-review-{language}.json", failures)
    if failures:
        print(
            language,
            len(failures),
            "forms require correction; catalogs unchanged",
            flush=True,
        )
        return False
    if dry_run:
        print(language, "ready:", len(prepared), "forms", flush=True)
        return True
    for path, _ in catalogs:
        backup = ROOT / "data/translation-originals" / language / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    recorded = set()
    for entry, index, target in prepared:
        if id(entry) not in recorded:
            if "fuzzy" in entry.flags:
                previous = entry.msgstr_plural if entry.msgid_plural else entry.msgstr
                entry.tcomment = (
                    entry.tcomment
                    + "\nPrevious inactive fuzzy translation: "
                    + json.dumps(previous, ensure_ascii=False)
                ).strip()
                entry.flags.remove("fuzzy")
            entry.tcomment = (entry.tcomment + "\n" + DRAFT).strip()
            recorded.add(id(entry))
        if index is None:
            entry.msgstr = target
        else:
            entry.msgstr_plural[index] = target
    from localization import save_catalog

    for path, catalog in catalogs:
        save_catalog(catalog, path)
    print(language, "saved", len(prepared), "forms", flush=True)
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("draft", "check", "apply"))
    parser.add_argument("languages", nargs="+")
    parser.add_argument(
        "--model", type=Path, default=ROOT / "data/translation-model-large"
    )
    args = parser.parse_args()
    languages = list(LANGUAGES) if args.languages == ["all"] else args.languages
    if any(language not in LANGUAGES for language in languages):
        parser.error("Choose an existing non-English locale")
    if args.command == "draft":
        model, tokenizer = load_model(args.model)
        for language in languages:
            draft(language, model, tokenizer)
    else:
        results = [
            apply(language, dry_run=args.command == "check") for language in languages
        ]
        if not all(results):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
