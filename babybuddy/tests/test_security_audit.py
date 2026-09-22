import csv
import io
import tempfile
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from core.models import Child, Note, Appointment
from core.calendar_tokens import feed_token


class SecurityAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "security-parent", is_staff=True, is_superuser=True
        )
        self.child = Child.objects.create(
            first_name="Sam", birth_date=timezone.localdate()
        )
        self.other = Child.objects.create(
            first_name="Alex", birth_date=timezone.localdate()
        )
        self.limited = get_user_model().objects.create_user(
            "limited-staff", is_staff=True
        )
        self.client.force_login(self.user)

    def grant(self, *codes):
        self.limited.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core", codename__in=codes
            )
        )
        self.limited = get_user_model().objects.get(pk=self.limited.pk)

    def feed_url(self, child=None):
        return reverse("core:appointment-feed", args=[(child or self.child).slug])

    def test_feed_token_is_child_scoped_read_only_and_not_an_api_key(self):
        token = feed_token(self.user, self.child)
        public = Client()
        response = public.get(self.feed_url(), {"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            public.get(self.feed_url(self.other), {"token": token}).status_code, 403
        )
        api_key = Token.objects.get(user=self.user).key
        self.assertNotIn(api_key, token)
        self.assertEqual(
            public.get(self.feed_url(), {"token": api_key}).status_code, 403
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token " + token)
        self.assertIn(client.get(reverse("api:child-list")).status_code, (401, 403))
        page = self.client.get(reverse("core:appointment-list"))
        self.assertContains(page, token)
        self.assertNotContains(page, api_key)

    def test_rotating_api_key_revokes_old_calendar_links(self):
        token = feed_token(self.user, self.child)
        Token.objects.filter(user=self.user).delete()
        self.assertEqual(
            Client().get(self.feed_url(), {"token": token}).status_code, 403
        )
        self.assertNotEqual(feed_token(self.user, self.child), token)

    def test_feed_rechecks_expiry_permissions_and_active_state(self):
        self.grant("view_appointment")
        token = feed_token(self.limited, self.child)
        public = Client()
        self.assertEqual(public.get(self.feed_url(), {"token": token}).status_code, 200)
        self.limited.settings.access_expires = timezone.now() - timedelta(minutes=1)
        self.limited.settings.save()
        self.assertEqual(public.get(self.feed_url(), {"token": token}).status_code, 403)
        self.limited.settings.access_expires = None
        self.limited.settings.save()
        self.limited.user_permissions.clear()
        self.assertEqual(public.get(self.feed_url(), {"token": token}).status_code, 403)
        self.grant("view_appointment")
        self.limited.is_active = False
        self.limited.save()
        self.assertEqual(public.get(self.feed_url(), {"token": token}).status_code, 403)

    def test_calendar_newlines_cannot_inject_events(self):
        self.child.first_name = "Sam\r\nBEGIN:VEVENT"
        self.child.save()
        Appointment.objects.create(
            child=self.child, title="Visit\r\nBEGIN:VEVENT", start=timezone.now()
        )
        response = Client().get(
            self.feed_url(), {"token": feed_token(self.user, self.child)}
        )
        self.assertEqual(
            response.content.decode().splitlines().count("BEGIN:VEVENT"), 1
        )

    def test_full_export_denies_staff_without_record_permissions(self):
        self.client.force_login(self.limited)
        self.assertEqual(self.client.get(reverse("babybuddy:export")).status_code, 403)
        self.grant("view_child", "view_feeding")
        self.assertEqual(self.client.get(reverse("babybuddy:export")).status_code, 403)
        self.assertIn(Client().get(reverse("babybuddy:export")).status_code, (302, 403))

    def test_csv_exports_escape_formulas_without_changing_stored_notes(self):
        malicious = '=HYPERLINK("https://example.invalid","open")'
        note = Note.objects.create(child=self.child, note=malicious)
        response = self.client.get(reverse("babybuddy:export"))
        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        rows = list(csv.DictReader(io.StringIO(archive.read("note.csv").decode())))
        self.assertEqual(rows[0]["note"], "'" + malicious)
        note.refresh_from_db()
        self.assertEqual(note.note, malicious)
        from babybuddy.exports import escape_formula

        for value in ["+1", "-1", "@SUM(1)", " =1", "\ttext", "\rtext"]:
            self.assertTrue(escape_formula(value).startswith("'"))
        self.assertEqual(escape_formula(-1), -1)

    def test_admin_csv_export_also_escapes_formulas(self):
        from core.admin import NoteAdmin
        from django.contrib.admin import site
        from django.test import RequestFactory
        from import_export.formats.base_formats import CSV

        Note.objects.create(child=self.child, note="=1+1")
        request = RequestFactory().get("/admin/")
        request.user = self.user
        content = NoteAdmin(Note, site).get_export_data(
            CSV(), request, Note.objects.all()
        )
        self.assertIn("'=1+1", content)

    def test_api_head_requires_same_permission_as_get(self):
        client = APIClient()
        client.force_authenticate(self.limited)
        for method in (client.get, client.head):
            self.assertEqual(method(reverse("api:child-list")).status_code, 403)
        self.grant("view_child")
        client.force_authenticate(self.limited)
        self.assertEqual(client.head(reverse("api:child-list")).status_code, 200)

    def test_private_media_requires_matching_record_permission(self):
        with tempfile.TemporaryDirectory() as media, override_settings(
            MEDIA_ROOT=media
        ):
            filename = default_storage.save(
                "notes/images/private.png", ContentFile(b"test-image")
            )
            url = "/media/" + filename
            self.assertEqual(Client().get(url).status_code, 403)
            self.client.force_login(self.limited)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.grant("view_child")
            self.assertEqual(self.client.get(url).status_code, 403)
            self.grant("view_note")
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(b"".join(response.streaming_content), b"test-image")
            response.close()
            api = Client()
            response = api.get(
                url,
                HTTP_AUTHORIZATION="Token "
                + Token.objects.create(user=self.limited).key,
            )
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_child_thumbnail_still_loads_through_protected_media(self):
        from imagekit.cachefiles import ImageCacheFile
        from imagekit.registry import generator_registry

        with tempfile.TemporaryDirectory() as media, override_settings(
            MEDIA_ROOT=media
        ):
            picture = io.BytesIO()
            Image.new("RGB", (100, 100), "blue").save(picture, format="PNG")
            self.child.picture.save("security.png", ContentFile(picture.getvalue()))
            generator = generator_registry.get(
                "imagekit:thumbnail", source=self.child.picture, width=40, height=40
            )
            thumbnail = ImageCacheFile(generator)
            url = thumbnail.url
            self.assertIn("child/picture/", url)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertEqual(Client().get(url).status_code, 403)

    def test_media_rejects_traversal_and_executable_content(self):
        with patch("babybuddy.media.default_storage.open") as opened:
            for path in (
                "notes/images/../../data/db.sqlite3",
                "notes/images/evil.html",
                "notes/images/evil.svg",
                "child/picture/..\\..\\secret.png",
            ):
                response = self.client.get("/media/" + path)
                self.assertEqual(response.status_code, 404)
            opened.assert_not_called()

    def test_local_signing_key_is_random_and_persistent(self):
        from babybuddy.development_key import local_secret_key

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            key = local_secret_key(first)
            self.assertGreaterEqual(len(key), 50)
            self.assertEqual(local_secret_key(first), key)
            self.assertNotEqual(local_secret_key(second), key)
