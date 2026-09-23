import datetime as dt
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import Child, Note, Pumping


class OfflineRefreshTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("cache-user")
        self.user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_child", "view_note", "view_pumping"]
            )
        )
        self.child = Child.objects.create(
            first_name="Allowed", birth_date=dt.date(2020, 1, 1)
        )
        self.other = Child.objects.create(
            first_name="Restricted", birth_date=dt.date(2020, 1, 1)
        )
        self.user.settings.restrict_children = True
        self.user.settings.save()
        self.user.settings.allowed_children.set([self.child])
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def context(self):
        return self.api.get("/api/offline-context")

    def test_snapshot_scopes_children_and_shared_pumping(self):
        now = timezone.now() - dt.timedelta(minutes=1)
        Note.objects.create(child=self.child, time=now, note="Visible")
        Note.objects.create(child=self.other, time=now, note="Private")
        Note.objects.create(
            child=self.child, time=now - dt.timedelta(days=8), note="Old"
        )
        Pumping.objects.create(
            start=now - dt.timedelta(minutes=5), end=now, amount=20, entry_unit="mL"
        )
        response = self.context()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        history = response.data["history"]
        self.assertEqual(len(history), 2)
        self.assertTrue(any(row["details"] == "Visible" for row in history))
        self.assertFalse(
            any(
                "Private" in row["details"] or "Old" in row["details"]
                for row in history
            )
        )
        self.assertTrue(
            any(
                row["key"].startswith("pumping:") and row["child"] == ""
                for row in history
            )
        )

    def test_read_permissions_rechecked_on_refresh(self):
        Note.objects.create(child=self.child, time=timezone.now(), note="Visible")
        self.assertEqual(len(self.context().data["history"]), 1)
        self.user.user_permissions.clear()
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.api.force_authenticate(self.user)
        self.assertEqual(self.context().data["history"], [])

    def test_snapshot_is_bounded_and_newest_first(self):
        now = timezone.now()
        Note.objects.bulk_create(
            [
                Note(child=self.child, time=now - dt.timedelta(minutes=i), note=str(i))
                for i in range(205)
            ]
        )
        rows = self.context().data["history"]
        self.assertEqual(len(rows), 200)
        self.assertEqual(rows[0]["details"], "0")
        self.assertEqual(rows[-1]["details"], "199")

    def test_anonymous_cannot_fetch_cached_data(self):
        self.api.force_authenticate(None)
        self.assertIn(self.context().status_code, (401, 403))
