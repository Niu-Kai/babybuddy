"""Regression coverage for the second agreed upstream issue batch."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from core import models
from core.forms import PumpingForm


class CurrentFollowupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "followup", "", "test-only"
        )
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.start = timezone.now() - timedelta(hours=2)
        self.end = self.start + timedelta(minutes=15)

    def child(self, name="Alex"):
        return models.Child.objects.create(
            first_name=name, birth_date=timezone.localdate()
        )

    def test_empty_household_redirects_then_returns_to_entry(self):
        target = reverse("core:feeding-add")
        response = self.client.get(target)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("core:child-add") + "?next="))
        response = self.client.post(
            response.url,
            {"first_name": "Alex", "birth_date": timezone.localdate().isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)
        self.assertEqual(self.client.get(target).status_code, 200)

    def test_no_child_permission_gives_guidance_and_shared_pumping_stays_available(
        self,
    ):
        user = get_user_model().objects.create_user("caregiver")
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=["add_feeding", "add_pumping"])
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:feeding-add"))
        self.assertContains(response, "administrator", status_code=403)
        self.assertEqual(self.client.get(reverse("core:pumping-add")).status_code, 200)

    def test_add_child_rejects_external_return_url(self):
        response = self.client.post(
            reverse("core:child-add") + "?next=https://example.org/",
            {"first_name": "Alex", "birth_date": timezone.localdate().isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:child-list"))

    def test_pumping_split_converts_both_sides_and_total(self):
        form = PumpingForm(
            {
                "start": self.start,
                "end": self.end,
                "left_amount": 2,
                "right_amount": 1,
                "entry_unit": "fl oz",
                "side": "both",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertAlmostEqual(entry.left_amount, 59.147059125)
        self.assertAlmostEqual(entry.right_amount, 29.5735295625)
        self.assertAlmostEqual(entry.amount, 88.7205886875)
        self.assertEqual(entry.side, "both")

    def test_pumping_api_split_partial_update_and_legacy_total(self):
        response = self.api.post(
            "/api/pumping/",
            {
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
                "left_amount": 30,
                "right_amount": 40,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], 70)
        url = f"/api/pumping/{response.data['id']}/"
        response = self.api.patch(url, {"right_amount": 50}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["amount"], 80)
        response = self.api.patch(url, {"amount": 100}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["left_amount"])
        self.assertIsNone(response.data["right_amount"])
        self.assertEqual(response.data["amount"], 100)

    def test_pumping_invalid_quantities_rejected(self):
        for values in ({}, {"left_amount": -1}, {"amount": -1}, {"left_amount": "NaN"}):
            with self.subTest(values=values):
                response = self.api.post(
                    "/api/pumping/",
                    {
                        "start": self.start.isoformat(),
                        "end": self.end.isoformat(),
                        **values,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(models.Pumping.objects.count(), 0)

    def test_medication_choices_latest_dose_and_child_access(self):
        child, other = self.child(), self.child("Sam")
        for hours, dose in ((4, 1), (2, 2)):
            models.Medication.objects.create(
                child=child,
                time=timezone.now() - timedelta(hours=hours),
                name="Example",
                dosage=dose,
                dosage_unit="mL",
                next_dose_interval=timedelta(hours=6),
            )
        models.Medication.objects.create(
            child=other,
            time=self.start,
            name="Other medicine",
            dosage=3,
            dosage_unit="mL",
        )
        user = get_user_model().objects.create_user("restricted")
        user.user_permissions.add(Permission.objects.get(codename="view_medication"))
        user.settings.restrict_children = True
        user.settings.save()
        user.settings.allowed_children.add(child)
        self.client.force_login(user)
        url = reverse("core:medication-choices")
        response = self.client.get(url, {"child": child.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["medications"],
            [
                {
                    "name": "Example",
                    "dosage": 2,
                    "dosage_unit": "mL",
                    "next_dose_interval": 6,
                }
            ],
        )
        self.assertEqual(
            self.client.get(url, {"child": other.pk}).json()["medications"], []
        )
        user.user_permissions.clear()
        self.assertEqual(self.client.get(url, {"child": child.pk}).status_code, 403)

    def test_caregiver_label_preserves_api_value(self):
        self.assertEqual(
            dict(models.Feeding._meta.get_field("method").choices)["parent fed"],
            "Caregiver fed",
        )

    def test_pumping_partial_save_keeps_total_consistent(self):
        entry = models.Pumping.objects.create(
            start=self.start, end=self.end, left_amount=10, right_amount=20
        )
        entry.left_amount = 30
        entry.save(update_fields=["left_amount"])
        entry.refresh_from_db()
        self.assertEqual(entry.amount, 50)
