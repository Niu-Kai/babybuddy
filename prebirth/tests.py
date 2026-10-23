from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Child
from .models import Plan, ChecklistItem, Contraction
from .views import contraction_state


class PreparationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "expecting-parent", "", "test"
        )
        self.client.force_login(self.user)
        self.url = reverse("prebirth:preparation")
        self.timer_url = reverse("prebirth:contractions")

    def test_available_without_a_child_and_starter_checklist_is_persistent(self):
        self.assertFalse(Child.objects.exists())
        page = self.client.get(self.url)
        self.assertContains(page, "Contraction timer")
        self.assertContains(page, "Hospital bag")
        self.assertContains(page, "rear-facing car seat")
        self.assertTrue(ChecklistItem.objects.filter(preset=True).exists())
        self.assertEqual(Plan.objects.count(), 1)

    def test_plan_notes_saved_and_escaped(self):
        response = self.client.post(
            self.url,
            {
                "action": "save-plan",
                "hospital": "Kaiser",
                "contact": "Labor & delivery",
                "phone": "555-0100",
                "due_date": "2027-01-10",
                "notes": "<script>unsafe</script>",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Plan.objects.get().hospital, "Kaiser")
        page = self.client.get(self.url)
        self.assertNotContains(page, "<script>unsafe</script>")
        self.assertContains(page, "&lt;script&gt;unsafe&lt;/script&gt;")

    def test_checklist_add_toggle_and_delete(self):
        self.client.post(
            self.url,
            {"action": "add-item", "label": "Spare charger", "category": "support"},
        )
        item = ChecklistItem.objects.get(label="Spare charger")
        for _ in range(2):
            response = self.client.post(
                self.url,
                {"action": "toggle-item", "id": item.pk, "packed": "1"},
                HTTP_ACCEPT="application/json",
            )
            self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.packed)
        self.client.post(self.url, {"action": "delete-item", "id": item.pk})
        self.assertFalse(ChecklistItem.objects.filter(pk=item.pk).exists())

    def test_contraction_start_stop_survives_refresh_and_is_idempotent(self):
        for _ in range(2):
            response = self.client.post(self.timer_url, {"action": "start"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Contraction.objects.count(), 1)
        entry = Contraction.objects.get()
        self.assertEqual(
            self.client.get(self.timer_url).json()["active"]["id"], entry.pk
        )
        with patch(
            "prebirth.views.timezone.now",
            return_value=entry.start + timedelta(seconds=65),
        ):
            response = self.client.post(
                self.timer_url,
                {"action": "stop", "id": entry.pk, "notes": "Lower back"},
            )
        self.assertIsNone(response.json()["active"])
        self.assertEqual(response.json()["records"][0]["duration"], 65)
        entry.refresh_from_db()
        self.assertEqual(entry.notes, "Lower back")
        original_end = entry.end
        self.client.post(self.timer_url, {"action": "stop", "id": entry.pk})
        entry.refresh_from_db()
        self.assertEqual(entry.end, original_end)
        self.assertEqual(entry.notes, "Lower back")

    def test_only_one_active_contraction_even_across_devices(self):
        Contraction.objects.create(created_by=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Contraction.objects.create(created_by=self.user)

    def test_intervals_are_start_to_start_and_summary_does_not_count_old_entries(self):
        now = timezone.now()
        for minutes in (80, 12, 7, 2):
            Contraction.objects.create(
                start=now - timedelta(minutes=minutes),
                end=now - timedelta(minutes=minutes) + timedelta(seconds=60),
            )
        data = contraction_state()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["average_duration"], 60)
        self.assertEqual(data["average_interval"], 300)
        self.assertEqual(data["records"][0]["interval"], 300)

    def test_read_only_role_cannot_start_timer_or_change_checklist(self):
        viewer = get_user_model().objects.create_user("prebirth-read-only")
        viewer.groups.add(Group.objects.get(name="read_only"))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.timer_url).status_code, 200)
        self.assertEqual(
            self.client.post(self.timer_url, {"action": "start"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                self.url, {"action": "add-item", "label": "No", "category": "baby"}
            ).status_code,
            403,
        )

    def test_caregiver_role_can_use_shared_pages_with_child_restrictions(self):
        caregiver = get_user_model().objects.create_user("prebirth-caregiver")
        caregiver.groups.add(Group.objects.get(name="caregiver"))
        caregiver.settings.restrict_children = True
        caregiver.settings.save()
        self.client.force_login(caregiver)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.post(self.timer_url, {"action": "start"}).status_code, 200
        )
        item = ChecklistItem.objects.first()
        self.assertEqual(
            self.client.post(
                self.url, {"action": "delete-item", "id": item.pk}
            ).status_code,
            403,
        )

    def test_permissions_csrf_and_invalid_input(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(self.timer_url, {"action": "start"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(self.timer_url, {"action": "unknown"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                self.timer_url, {"action": "stop", "id": "bad"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                self.url, {"action": "toggle-item", "id": "bad"}
            ).status_code,
            404,
        )
        stranger = get_user_model().objects.create_user("no-prebirth-permissions")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.timer_url).status_code, 403)
