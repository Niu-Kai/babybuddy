# -*- coding: utf-8 -*-
import re
import time

from django.test import TestCase, override_settings
from django.test import Client as HttpClient
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from faker import Faker

from babybuddy.views import UserUnlock


class ViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(ViewsTestCase, cls).setUpClass()
        fake = Faker()
        call_command("migrate", verbosity=0)

        cls.c = HttpClient()

        fake_user = fake.simple_profile()
        cls.credentials = {
            "username": fake_user["username"],
            "password": fake.password(),
        }
        cls.user = get_user_model().objects.create_user(
            is_superuser=True, email="admin@admin.admin", **cls.credentials
        )

        cls.c.login(**cls.credentials)

    def test_root_router(self):
        page = self.c.get("/")
        self.assertEqual(page.url, "/dashboard/")

    @override_settings(ROLLING_SESSION_REFRESH=1)
    def test_rolling_sessions(self):
        self.c.get("/")
        session1 = str(self.c.cookies["sessionid"])
        # Sleep longer than ROLLING_SESSION_REFRESH.
        time.sleep(2)
        self.c.get("/")
        session2 = str(self.c.cookies["sessionid"])
        self.c.get("/")
        session3 = str(self.c.cookies["sessionid"])
        self.assertNotEqual(session1, session2)
        self.assertEqual(session2, session3)

    def test_user_settings(self):
        page = self.c.get("/user/settings/")
        self.assertEqual(page.status_code, 200)

    def test_api_key_regenerate(self):
        original_key = str(self.user.settings.api_key())
        page = self.c.post("/user/settings/", {"api_key_regenerate": ""}, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertNotEqual(str(self.user.settings.api_key()), original_key)

    def test_add_device_page(self):
        page = self.c.get("/user/add-device/")
        self.assertRegex(
            page.content.decode(),
            r""".*<div [^>]* data-qr-code-content="[^"]+"[^>]*>.*""",
        )

    def test_user_views(self):
        # Staff setting is required to access user management.
        page = self.c.get("/users/")
        self.assertEqual(page.status_code, 403)
        self.user.is_staff = True
        self.user.save()

        page = self.c.get("/users/")
        self.assertEqual(page.status_code, 200)
        page = self.c.get("/users/add/")
        self.assertEqual(page.status_code, 200)

        entry = get_user_model().objects.first()
        page = self.c.get("/users/{}/edit/".format(entry.id))
        self.assertEqual(page.status_code, 200)
        page = self.c.get("/users/{}/delete/".format(entry.id))
        self.assertEqual(page.status_code, 200)

    def test_user_unlock(self):
        # Staff setting is required to unlock users.
        self.user.is_staff = True
        self.user.save()

        entry = get_user_model().objects.first()
        url = "/users/{}/unlock/".format(entry.id)

        page = self.c.get(url)
        self.assertEqual(page.status_code, 200)
        page = self.c.post(url, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, UserUnlock.success_message)

    def test_welcome(self):
        page = self.c.get("/welcome/")
        self.assertEqual(page.status_code, 200)

    def test_logout_get_fails(self):
        page = self.c.get("/logout/")
        self.assertEqual(page.status_code, 405)

    def test_password_reset(self):
        """
        Testing this class primarily ensures Baby Buddy's custom templates are correctly
        configured for Django's password reset flow.

        This test logs out, which would leave every later test in this class using
        a logged-out client, so it takes its own client rather than the shared
        `self.c`.
        """
        client = HttpClient()

        page = client.get("/reset/")
        self.assertEqual(page.status_code, 200)

        page = client.post("/reset/", data={"email": self.user.email}, follow=True)
        self.assertEqual(page.status_code, 200)

        self.assertEqual(len(mail.outbox), 1)

        path = re.search(
            "http://testserver(?P<path>[^\\s]+)", mail.outbox[0].body
        ).group("path")
        page = client.get(path, follow=True)
        self.assertEqual(page.status_code, 200)

        new_password = "xZZVN6z4TvhFg6S"
        data = {
            "new_password1": new_password,
            "new_password2": new_password,
        }
        page = client.post(page.request["PATH_INFO"], data=data, follow=True)
        self.assertEqual(page.status_code, 200)


class ErrorPageTestCase(TestCase):
    """
    The 404 template is only rendered with `DEBUG` off, which no other test
    exercises, so a syntax error in it went unnoticed.
    """

    @classmethod
    def setUpClass(cls):
        super(ErrorPageTestCase, cls).setUpClass()
        fake = Faker()
        cls.c = HttpClient()
        fake_user = fake.simple_profile()
        cls.credentials = {
            "username": fake_user["username"],
            "password": fake.password(),
        }
        get_user_model().objects.create_user(is_superuser=True, **cls.credentials)

    @override_settings(DEBUG=False)
    def test_404_page_renders(self):
        self.c.login(**self.credentials)
        page = self.c.get("/this-path-does-not-exist/")
        self.assertEqual(page.status_code, 404)
        self.assertIn("Page Not Found", page.content.decode())
        self.assertIn("/this-path-does-not-exist/", page.content.decode())


class ThemeTestCase(TestCase):
    """A user can pick a light, dark or device-matching theme (#785)."""

    def setUp(self):
        call_command("migrate", verbosity=0)
        self.credentials = {"username": "theme", "password": "theme-pass"}
        self.user = get_user_model().objects.create_user(
            is_superuser=True, **self.credentials
        )
        self.c = HttpClient()
        self.c.login(**self.credentials)

    def _set(self, theme):
        self.user.settings.theme = theme
        self.user.settings.save()

    def test_default_is_dark(self):
        page = self.c.get("/user/settings/")
        self.assertContains(page, 'data-bs-theme="dark"')
        self.assertNotContains(page, "prefers-color-scheme")

    def test_light(self):
        self._set("light")
        page = self.c.get("/user/settings/")
        self.assertContains(page, 'data-bs-theme="light"')

    def test_auto_follows_device(self):
        self._set("auto")
        page = self.c.get("/user/settings/")
        self.assertContains(page, "prefers-color-scheme")

    def test_anonymous_is_dark(self):
        page = HttpClient().get("/login/")
        self.assertContains(page, 'data-bs-theme="dark"')


class PreferencesTestCase(TestCase):
    """24-hour clock, device time zone, dashboard cards and export."""

    def setUp(self):
        call_command("migrate", verbosity=0)
        self.credentials = {"username": "prefs", "password": "prefs-pass"}
        self.user = get_user_model().objects.create_user(
            is_superuser=True, is_staff=True, **self.credentials
        )
        self.c = HttpClient()
        self.c.login(**self.credentials)
        # Other tests may leave a different zone active on this thread.
        self.user.settings.timezone = "UTC"
        self.user.settings.save()
        timezone.activate("UTC")
        from core import models as core_models

        self.child = core_models.Child.objects.create(
            first_name="Pref", last_name="Kid", birth_date=timezone.localdate()
        )
        start = timezone.localtime().replace(hour=13, minute=5, second=0, microsecond=0)
        if start > timezone.localtime():
            start -= timezone.timedelta(days=1)
        core_models.Feeding.objects.create(
            child=self.child, start=start, end=start, type="formula", method="bottle"
        )

    def test_24_hour_clock(self):
        page = self.c.get("/feedings/")
        self.assertContains(page, "1:05 p.m.")
        self.user.settings.use_24_hour_time = True
        self.user.settings.save()
        page = self.c.get("/feedings/")
        self.assertContains(page, "13:05")
        self.assertNotContains(page, "1:05 p.m.")

    def test_device_timezone(self):
        self.user.settings.timezone = "UTC"
        self.user.settings.timezone_follow_device = True
        self.user.settings.save()
        self.c.cookies["babybuddy_device_tz"] = "Asia/Tokyo"
        page = self.c.get("/feedings/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "10:05 p.m.")
        self.assertEqual(timezone.get_current_timezone_name(), "UTC")
        timezone.deactivate()
        self.c.cookies["babybuddy_device_tz"] = "Not/AZone"
        page = self.c.get("/feedings/")
        self.assertEqual(page.status_code, 200)
        timezone.deactivate()

    def test_dashboard_cards(self):
        page = self.c.get("/children/{}/dashboard/".format(self.child.slug))
        self.assertContains(page, "Last Sleep")
        self.user.settings.dashboard_hidden_cards = ["sleep_last"]
        self.user.settings.save()
        page = self.c.get("/children/{}/dashboard/".format(self.child.slug))
        self.assertNotContains(page, "Last Sleep")
        self.assertContains(page, "Last Feeding")

    def test_dashboard_cards_form(self):
        params = {
            "first_name": "",
            "last_name": "",
            "email": "",
            "dashboard_refresh_rate": "0:01:00",
            "language": "en-US",
            "timezone": "UTC",
            "pagination_count": 25,
            "dashboard_cards_present": "1",
            "dashboard_cards": ["feeding_last", "statistics"],
        }
        page = self.c.post("/user/settings/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.user.settings.refresh_from_db()
        self.assertIn("sleep_last", self.user.settings.dashboard_hidden_cards)
        self.assertNotIn("feeding_last", self.user.settings.dashboard_hidden_cards)

    def test_export(self):
        page = self.c.get("/export/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page["Content-Type"], "application/zip")
        import io
        import zipfile

        archive = zipfile.ZipFile(io.BytesIO(page.content))
        self.assertIn("child.csv", archive.namelist())
        self.assertIn("feeding.csv", archive.namelist())
        self.assertIn("Pref", archive.read("child.csv").decode())

    def test_corrected_age(self):
        self.child.birth_date = timezone.localdate() - timezone.timedelta(days=60)
        self.child.due_date = timezone.localdate() - timezone.timedelta(days=10)
        self.child.save()
        page = self.c.get("/children/{}/dashboard/".format(self.child.slug))
        self.assertContains(page, "Corrected age")
        self.assertEqual(self.child.corrected_birth_date, self.child.due_date)


class ServiceWorkerTestCase(TestCase):
    def test_service_worker_served(self):
        page = HttpClient().get("/sw.js")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page["Content-Type"], "application/javascript")
        self.assertEqual(page["Service-Worker-Allowed"], "/")
        self.assertIn("addEventListener", page.content.decode())
