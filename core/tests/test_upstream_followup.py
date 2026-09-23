import uuid
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from core import models
from core.calendar_tokens import feed_token
from inventory.models import Equipment, StockItem, ChildSupplyProfile
from babybuddy.models import OfflineReceipt


class FollowupTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            "reviewadmin", "", "test-only"
        )
        self.caregiver = get_user_model().objects.create_user("reviewcarer")
        self.caregiver.groups.add(
            Group.objects.get(name=settings.BABY_BUDDY["CAREGIVER_GROUP_NAME"])
        )
        self.child = models.Child.objects.create(
            first_name="Allowed",
            last_name="Baby",
            birth_date=timezone.localdate() - timezone.timedelta(days=30),
        )
        self.other = models.Child.objects.create(
            first_name="Private", last_name="Baby", birth_date=self.child.birth_date
        )
        self.when = timezone.now() - timezone.timedelta(hours=2)
        self.client.force_login(self.admin)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def restrict(self):
        self.caregiver.settings.restrict_children = True
        self.caregiver.settings.save()
        self.caregiver.settings.allowed_children.set([self.child])
        self.client.force_login(self.caregiver)
        self.api.force_authenticate(self.caregiver)

    def feeding(self, **extra):
        return {
            "child": self.child.pk,
            "start": self.when.isoformat(),
            "end": self.when.isoformat(),
            "type": "formula",
            "method": "bottle",
            **extra,
        }

    def test_feeding_validation_on_create_and_patch(self):
        self.assertEqual(
            self.api.post(
                "/api/feedings/", self.feeding(method="left breast"), format="json"
            ).status_code,
            400,
        )
        response = self.api.post("/api/feedings/", self.feeding(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            self.api.patch(
                f"/api/feedings/{response.data['id']}/",
                {"method": "both breasts"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.api.post(
                "/api/feedings/", self.feeding(type="solid food"), format="json"
            ).status_code,
            400,
        )

    def test_equipment_converts_units_and_uses_latest_record(self):
        item = Equipment.objects.create(
            name="Bassinet", weight_limit=10, weight_unit="lb"
        )
        item.children.add(self.child)
        models.Weight.objects.create(
            child=self.child, weight=5, date=timezone.localdate(), entry_unit="kg"
        )
        models.Weight.objects.create(
            child=self.child,
            weight=3,
            date=timezone.localdate() - timezone.timedelta(days=1),
            entry_unit="kg",
        )
        assessment = item.assessments()[0]
        self.assertTrue(assessment["attention"])
        self.assertAlmostEqual(assessment["checks"][0]["value"], 11.0231, places=3)
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "Equipment needs review")
        self.assertContains(self.client.get(reverse("inventory:equipment")), "Bassinet")

    def test_restricted_html_api_and_assignment(self):
        entry = models.DiaperChange.objects.create(
            child=self.other, time=self.when, wet=True, solid=False
        )
        self.restrict()
        response = self.client.get(reverse("core:diaperchange-list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private Baby")
        self.assertEqual(
            self.client.get(
                reverse("core:diaperchange-update", args=[entry.pk])
            ).status_code,
            404,
        )
        self.assertEqual(self.api.get(f"/api/changes/{entry.pk}/").status_code, 404)
        self.assertEqual(
            self.api.post(
                "/api/changes/",
                {
                    "child": self.other.pk,
                    "wet": True,
                    "solid": False,
                    "time": self.when.isoformat(),
                },
                format="json",
            ).status_code,
            400,
        )
        response = self.client.get(reverse("core:timeline"))
        self.assertNotContains(response, "Private Baby")
        self.assertEqual(self.client.get(reverse("inventory:list")).status_code, 200)

    def test_token_auth_scopes_children_and_dashboard(self):
        self.restrict()
        self.api.force_authenticate(None)
        self.api.credentials(
            HTTP_AUTHORIZATION="Token "
            + Token.objects.get_or_create(user=self.caregiver)[0].key
        )
        response = self.api.get("/api/dashboard")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [child["id"] for child in response.data["children"]], [self.child.pk]
        )
        children = self.api.get("/api/children/").data["results"]
        self.assertEqual([child["id"] for child in children], [self.child.pk])

    def test_calendar_token_rechecks_child_access(self):
        token = feed_token(self.caregiver, self.other)
        self.restrict()
        self.client.logout()
        response = self.client.get(
            reverse("core:appointment-feed", args=[self.other.slug]), {"token": token}
        )
        self.assertEqual(response.status_code, 403)

    def test_offline_retry_deducts_diaper_once(self):
        item = StockItem.objects.create(
            name="Diapers", category="diapers", unit="diapers", quantity=20
        )
        ChildSupplyProfile.objects.create(child=self.child, diaper_stock=item)
        payload = {
            "key": str(uuid.uuid4()),
            "user": self.admin.pk,
            "activity": "diaperchange",
            "entry": {
                "child": self.child.pk,
                "time": self.when.isoformat(),
                "wet": True,
                "solid": False,
            },
        }
        first = self.api.post("/api/offline-sync", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        retry = self.api.post("/api/offline-sync", payload, format="json")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertTrue(retry.data["duplicate"])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 19)
        self.assertEqual(models.DiaperChange.objects.count(), 1)
        payload["entry"]["solid"] = True
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 400
        )

    def test_offline_errors_roll_back_receipts_and_wrong_account_rejected(self):
        payload = {
            "key": str(uuid.uuid4()),
            "user": self.admin.pk,
            "activity": "feeding",
            "unit": "mL",
            "entry": self.feeding(method="left breast"),
        }
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 400
        )
        self.assertEqual(OfflineReceipt.objects.count(), 0)
        self.restrict()
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 403
        )
        payload.update(user=self.caregiver.pk, entry=self.feeding(child=self.other.pk))
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 403
        )

    def test_offline_unit_conversion_and_bootstrap(self):
        response = self.api.get("/api/offline-context")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreater(len(response.data["activities"]), 10)
        payload = {
            "key": str(uuid.uuid4()),
            "user": self.admin.pk,
            "activity": "weight",
            "unit": "lb",
            "entry": {
                "child": self.child.pk,
                "date": timezone.localdate().isoformat(),
                "weight": 10,
            },
        }
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 201
        )
        self.assertAlmostEqual(models.Weight.objects.get().weight, 4.5359237)
        shell = self.client.get(reverse("babybuddy:offline"))
        self.assertNotContains(shell, "Allowed Baby")
        self.assertNotContains(shell, "reviewadmin")

    def test_custom_activity_pages_and_timeline(self):
        definition = models.ActivityType.objects.create(
            name="Story time",
            track_duration=True,
            amount_label="Books",
            check_label="Enjoyed it",
        )
        response = self.client.get(
            reverse("core:customactivity-add"), {"activity_type": definition.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Books")
        response = self.api.post(
            "/api/custom-activities/",
            {
                "child": self.child.pk,
                "activity_type": definition.pk,
                "start": self.when.isoformat(),
                "end": self.when.isoformat(),
                "amount": 2,
                "checked": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertContains(self.client.get(reverse("core:timeline")), "Story time")
        self.assertContains(
            self.client.get(reverse("core:customactivity-list")), "Story time"
        )

    def test_timer_context_prefills_api_and_form(self):
        timer = models.Timer.objects.create(
            user=self.admin,
            child=self.child,
            start=self.when,
            context={
                "activity": "feeding",
                "type": "breast milk",
                "method": "left breast",
            },
        )
        response = self.client.get(reverse("core:feeding-add"), {"timer": timer.pk})
        self.assertEqual(response.context["form"].initial["method"], "left breast")
        response = self.api.post("/api/feedings/", {"timer": timer.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(models.Feeding.objects.get().method, "left breast")

    def test_hidden_fields_preserve_data(self):
        self.admin.settings.hidden_entry_fields = ["notes"]
        self.admin.settings.save()
        entry = models.Feeding.objects.create(
            child=self.child,
            start=self.when,
            end=self.when,
            type="formula",
            method="bottle",
            notes="Keep me",
        )
        response = self.client.get(reverse("core:feeding-update", args=[entry.pk]))
        form = response.context["form"]
        self.assertTrue(form.fields["notes"].disabled)
        self.assertTrue(form.fields["notes"].widget.is_hidden)

    def test_restricted_equipment_form_preserves_other_assignments(self):
        item = Equipment.objects.create(name="Shared gear")
        item.children.add(self.child, self.other)
        self.restrict()
        response = self.client.get(reverse("inventory:equipment-edit", args=[item.pk]))
        self.assertNotContains(response, "Private Baby")
        response = self.client.post(
            reverse("inventory:equipment-edit", args=[item.pk]),
            {
                "name": "Shared gear",
                "children": [self.child.pk],
                "weight_unit": "lb",
                "height_unit": "in",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(item.children.values_list("pk", flat=True)),
            {self.child.pk, self.other.pk},
        )

    def test_child_scope_does_not_leak_to_next_request(self):
        self.restrict()
        self.assertEqual(len(self.api.get("/api/dashboard").data["children"]), 1)
        self.api.force_authenticate(self.admin)
        self.assertEqual(len(self.api.get("/api/dashboard").data["children"]), 2)
        self.assertEqual(models.Child.objects.count(), 2)

    def test_empty_household_create_pages_do_not_crash(self):
        models.Child.objects.all().delete()
        for name in ("feeding", "diaperchange", "sleep", "medication"):
            self.assertEqual(
                self.client.get(reverse(f"core:{name}-add")).status_code, 302
            )

    def test_offline_revoked_child_cannot_replay_previous_receipt(self):
        self.restrict()
        payload = {
            "key": str(uuid.uuid4()),
            "user": self.caregiver.pk,
            "activity": "diaperchange",
            "entry": {
                "child": self.child.pk,
                "time": self.when.isoformat(),
                "wet": True,
                "solid": False,
            },
        }
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 201
        )
        self.caregiver.settings.allowed_children.clear()
        self.api.force_authenticate(get_user_model().objects.get(pk=self.caregiver.pk))
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 403
        )

    def test_sleep_interval_uses_same_child_across_filter_boundary(self):
        older = models.Sleep.objects.create(
            child=self.child,
            start=self.when - timezone.timedelta(hours=4),
            end=self.when - timezone.timedelta(hours=3),
            nap=True,
        )
        models.Sleep.objects.create(
            child=self.other,
            start=self.when - timezone.timedelta(hours=2),
            end=self.when - timezone.timedelta(hours=1),
            nap=True,
        )
        latest = models.Sleep.objects.create(
            child=self.child,
            start=self.when,
            end=self.when + timezone.timedelta(minutes=15),
            nap=True,
        )
        response = self.client.get(reverse("core:sleep-list"))
        record = next(
            entry for entry in response.context["object_list"] if entry.pk == latest.pk
        )
        self.assertEqual(record.previous_entry_end, older.end)

    def test_restricted_media_denies_unassigned_child_before_opening_file(self):
        models.Note.objects.create(
            child=self.other,
            time=self.when,
            note="Private",
            image="notes/images/restricted.png",
        )
        self.other.picture = "child/picture/restricted.png"
        self.other.save()
        self.restrict()
        with patch("babybuddy.media.default_storage.open") as opened:
            for path in (
                "/media/notes/images/restricted.png",
                "/media/child/picture/restricted.png",
                "/media/CACHE/images/child/picture/restricted/hash.png",
            ):
                self.assertEqual(self.client.get(path).status_code, 404)
            opened.assert_not_called()

    def test_archived_custom_type_rejects_new_api_entries(self):
        definition = models.ActivityType.objects.create(
            name="Archived activity", archived=True
        )
        response = self.api.post(
            "/api/custom-activities/",
            {
                "child": self.child.pk,
                "activity_type": definition.pk,
                "start": self.when.isoformat(),
                "end": self.when.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_offline_solids_cannot_acquire_liquid_units(self):
        payload = {
            "key": str(uuid.uuid4()),
            "user": self.admin.pk,
            "activity": "feeding",
            "unit": "mL",
            "entry": self.feeding(type="solid food", method="parent fed"),
        }
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 400
        )
        self.assertEqual(OfflineReceipt.objects.count(), 0)
