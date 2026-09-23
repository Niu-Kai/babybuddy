"""Language activation, catalog discovery, and template syntax regressions."""

from pathlib import Path
from types import SimpleNamespace
from django.conf import settings
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory
from django.template import engines
from django.urls import reverse
from django.utils import translation
from babybuddy.middleware import UserLanguageMiddleware


class LocalizationTests(SimpleTestCase):
    def test_chinese_catalogs_match_django_locale_names(self):
        for language, save in (("zh-hans", "保存"), ("zh-hant", "儲存")):
            with self.subTest(language=language), translation.override(language):
                self.assertEqual(translation.gettext("Save"), save)
                self.assertEqual(translation.gettext("Sleep"), "睡眠")
        folders = {p.name for p in Path(settings.LOCALE_PATHS[0]).iterdir()}
        self.assertTrue({"zh_Hans", "zh_Hant"} <= folders)
        self.assertFalse({"zh_HANS", "zh_HANT"} & folders)

    def test_user_language_is_reflected_and_restored_after_error(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(settings=SimpleNamespace(language="fr"))
        request.LANGUAGE_CODE = "en-us"

        def response(request):
            self.assertEqual(request.LANGUAGE_CODE, "fr")
            return HttpResponse(translation.gettext("Sleep"))

        with translation.override("en-us"):
            result = UserLanguageMiddleware(response)(request)
            self.assertEqual(result.content.decode(), "Sommeil")
            self.assertEqual(result["Content-Language"], "fr")
            self.assertEqual(translation.get_language(), "en-us")

            def failure(request):
                raise ValueError("render failed")

            with self.assertRaises(ValueError):
                UserLanguageMiddleware(failure)(request)
            self.assertEqual(translation.get_language(), "en-us")

    def test_public_javascript_catalog_has_explicit_language(self):
        from babybuddy.localization import InterfaceCatalog
        from django.http import Http404

        request = RequestFactory().get("/")
        response = InterfaceCatalog.as_view()(request, language="fr")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Language"], "fr")
        self.assertIn("public", response["Cache-Control"])
        self.assertIn("django.gettext", response.content.decode())
        with self.assertRaises(Http404):
            InterfaceCatalog.as_view()(request, language="unsupported-language")

    def test_all_app_templates_compile(self):
        engine = engines["django"].engine
        for app in ("babybuddy", "core", "dashboard", "reports", "inventory"):
            for path in Path(settings.BASE_DIR, app, "templates").rglob("*.html"):
                with self.subTest(path=path):
                    engine.from_string(path.read_text(encoding="utf-8"))

    def test_new_care_labels_are_available_in_every_language(self):
        for language, _label in settings.LANGUAGES:
            if language.lower().startswith("en"):
                continue
            with self.subTest(language=language), translation.override(language):
                for message in (
                    "Left breast amount",
                    "Right breast amount",
                    "Pumping & nursing",
                    "Automatic reminders",
                    "Other measurements",
                    "Daily care",
                    "Health",
                    "+ Add entry",
                ):
                    self.assertNotEqual(translation.gettext(message), message)
                for count in (0, 1, 2, 5, 21):
                    label = translation.ngettext(
                        "%(count)s appointment", "%(count)s appointments", count
                    )
                    self.assertIn(str(count), label % {"count": count})

    def test_reviewed_care_terminology_and_event_plurals(self):
        with translation.override("fr"):
            self.assertEqual(
                translation.ngettext(
                    "%(count)s appointment", "%(count)s appointments", 2
                )
                % {"count": 2},
                "2 rendez-vous",
            )
        with translation.override("zh-hant"):
            self.assertEqual(translation.gettext("Offline log"), "離線紀錄")
            self.assertEqual(translation.gettext("Calendar"), "日曆")
        with translation.override("ja"):
            self.assertEqual(translation.gettext("Left breast amount"), "左胸の搾乳量")
            self.assertEqual(translation.gettext("Right breast amount"), "右胸の搾乳量")
        with translation.override("es"):
            self.assertEqual(translation.ngettext("wipe", "wipes", 1), "toallita")
            self.assertEqual(translation.ngettext("wipe", "wipes", 2), "toallitas")
