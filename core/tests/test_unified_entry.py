import datetime as dt
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from core import models
from babybuddy.models import OfflineReceipt


class UnifiedEntryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "unified", is_superuser=True, is_staff=True
        )
        self.child = models.Child.objects.create(
            first_name="Baby", birth_date=dt.date(2020, 1, 1)
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.client.force_login(self.user)

    def payload(self, activity="note", **fields):
        return {
            "key": str(uuid.uuid4()),
            "user": self.user.pk,
            "activity": activity,
            "format": "form",
            "entry": {
                "timezone": "America/New_York",
                "fields": {
                    "child": [str(self.child.pk)],
                    "appointment_date": ["2024-01-02"],
                    "start_time": ["8:00 AM"],
                    **{key: [value] for key, value in fields.items()},
                },
            },
        }

    def test_regular_note_form_saves_once_with_original_time_and_tags(self):
        data = self.payload(note="From regular entry", tags="home")
        first = self.api.post("/api/offline-sync", data, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        again = self.api.post("/api/offline-sync", data, format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(models.Note.objects.count(), 1)
        note = models.Note.objects.get()
        self.assertEqual(note.note, "From regular entry")
        self.assertEqual(note.time.hour, 13)
        self.assertEqual(list(note.tags.names()), ["home"])
        self.assertEqual(note.created_by_id, self.user.pk)

    def test_full_feeding_fields_and_unit_conversion_are_retained(self):
        data = self.payload(
            "feeding",
            duration_minutes="20",
            type="breast milk",
            method="left breast",
            entry_unit="fl oz",
            top_up_reference="present",
            top_up_enabled="on",
            top_up_date="2024-01-02",
            top_up_time="8:30 AM",
            top_up_type="formula",
            top_up_amount="2",
            notes="Keep this",
        )
        response = self.api.post("/api/offline-sync", data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        entry = models.Feeding.objects.get()
        self.assertAlmostEqual(entry.top_up_amount, 59.147059125)
        self.assertEqual(entry.notes, "Keep this")
        self.assertEqual(entry.top_up_at.hour, 13)
        self.assertEqual(entry.duration, dt.timedelta(minutes=20))

    def test_invalid_entry_stays_retryable_and_overlap_needs_confirmation(self):
        data = self.payload("sleep", duration_minutes="30")
        self.assertEqual(
            self.api.post("/api/offline-sync", data, format="json").status_code, 201
        )
        data["key"] = str(uuid.uuid4())
        response = self.api.post("/api/offline-sync", data, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("allow_overlap", response.data)
        self.assertFalse(OfflineReceipt.objects.filter(key=data["key"]).exists())
        data["entry"]["fields"]["allow_overlap"] = ["on"]
        self.assertEqual(
            self.api.post("/api/offline-sync", data, format="json").status_code, 201
        )

    def test_form_replay_checks_child_access_and_rejects_credentials(self):
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename="add_note"))
        self.user.settings.restrict_children = True
        self.user.settings.save()
        response = self.api.post(
            "/api/offline-sync", self.payload(note="Blocked"), format="json"
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.user.settings.allowed_children.add(self.child)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.api.force_authenticate(self.user)
        data = self.payload(note="Secret", csrfmiddlewaretoken="never cache")
        self.assertEqual(
            self.api.post("/api/offline-sync", data, format="json").status_code, 400
        )
        self.assertEqual(models.Note.objects.count(), 0)

    def test_navigation_settings_and_add_form_hooks(self):
        page = self.client.get("/", follow=True)
        self.assertNotContains(page, 'href="/offline/"')
        self.assertContains(page, 'id="device-sync-indicator"')
        settings = self.client.get("/user/settings/")
        self.assertContains(settings, 'id="device-sync-enable"')
        add = self.client.get("/notes/add/")
        self.assertContains(add, 'data-queued-entry="note"')
        self.assertNotContains(self.client.get("/entries/add/"), 'id="enable-offline"')

    def test_context_contains_entry_routes_and_child_slugs(self):
        data = self.api.get("/api/offline-context").data
        self.assertEqual(
            next(a for a in data["activities"] if a["key"] == "feeding")["add_url"],
            "/feedings/add/",
        )
        self.assertEqual(data["children"][0]["slug"], self.child.slug)
