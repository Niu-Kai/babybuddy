"""Offline catalog safeguards; no model, network, or application database needed."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polib
import local_translation as drafts


class DraftSafetyTests(unittest.TestCase):
    def test_round_trip_preserves_markup_variables_and_newlines(self):
        source = "Hello {user}: <code>%(path)s</code>\n%(count)s entries"
        protected, tokens = drafts.protect(source)
        self.assertEqual(drafts.restore(protected, tokens), source)
        with self.assertRaises(ValueError):
            drafts.restore(protected.replace("812310", ""), tokens)
        with self.assertRaises(ValueError):
            drafts.restore(protected + "812310", tokens)

    def test_refuses_new_markup_and_broken_variables(self):
        entry = polib.POEntry(msgid="Hello {user}")
        for target in ("Hello {usuario}", "<script>Hello {user}</script>", "⁇ {user}"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                drafts.validate(entry, target)

    def test_apply_preserves_active_text_and_keeps_fuzzy_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "locale/es/LC_MESSAGES"
            folder.mkdir(parents=True)
            (root / "data").mkdir()
            catalog = polib.POFile()
            catalog.metadata = {
                "Content-Type": "text/plain; charset=UTF-8",
                "Plural-Forms": "nplurals=2; plural=(n != 1);",
            }
            catalog.extend(
                [
                    polib.POEntry(msgid="Existing", msgstr="Texto revisado"),
                    polib.POEntry(msgid="New", msgstr="Texto antiguo", flags=["fuzzy"]),
                    polib.POEntry(msgid="Hello {user}", msgstr=""),
                ]
            )
            path = folder / "django.po"
            catalog.save(str(path))
            original = path.read_bytes()
            manifest = {"django": [[None, entry.msgid, ""] for entry in catalog]}
            drafts.save_json(root / "data/interface-messages.json", manifest)
            cache = {
                "Existing": "Must not replace",
                "New": "Texto nuevo",
                "Hello {user}": "Hola {usuario}",
            }
            drafts.save_json(root / "data/local-translation-es.json", cache)
            with patch.object(drafts, "ROOT", root):
                self.assertFalse(drafts.apply("es"))
                self.assertEqual(path.read_bytes(), original)
                cache["Hello {user}"] = "Hola {user}"
                drafts.save_json(root / "data/local-translation-es.json", cache)
                self.assertTrue(drafts.apply("es", dry_run=True))
                self.assertEqual(path.read_bytes(), original)
                self.assertTrue(drafts.apply("es"))
            result = polib.pofile(str(path))
            self.assertEqual(result.find("Existing").msgstr, "Texto revisado")
            self.assertEqual(result.find("New").msgstr, "Texto nuevo")
            self.assertNotIn("fuzzy", result.find("New").flags)
            self.assertIn("Texto antiguo", result.find("New").tcomment)
            self.assertEqual(
                (root / "data/translation-originals/es/django.po").read_bytes(),
                original,
            )


if __name__ == "__main__":
    unittest.main()
