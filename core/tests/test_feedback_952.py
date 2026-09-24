import datetime as dt
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from core import models


class TwinsFeedbackTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "feedback", password="test"
        )
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Test", last_name="Baby", birth_date=dt.date(2020, 1, 1)
        )
        self.timer = models.Timer.objects.create(
            user=self.user,
            child=self.child,
            start=timezone.now() - dt.timedelta(minutes=45),
        )
        self.url = reverse("core:timer-restart", args=[self.timer.pk])

    def test_restart_requires_confirmation_and_preserves_paused_time_until_confirmed(
        self,
    ):
        self.timer.pause()
        start, paused = self.timer.start, self.timer.paused_at
        response = self.client.post(self.url)
        self.assertContains(response, "Restarting resets the elapsed time.")
        self.assertContains(response, "Test Baby")
        self.timer.refresh_from_db()
        self.assertEqual((self.timer.start, self.timer.paused_at), (start, paused))
        token = response.context["confirmation"]
        response = self.client.post(self.url, {"confirmation": token})
        self.assertRedirects(
            response, reverse("core:timer-detail", args=[self.timer.pk])
        )
        self.timer.refresh_from_db()
        self.assertGreater(self.timer.start, start)
        self.assertIsNone(self.timer.paused_at)
        self.assertEqual(self.timer.paused_total, dt.timedelta())
        restarted = self.timer.start
        response = self.client.post(self.url, {"confirmation": token})
        self.assertContains(response, "This timer changed.")
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.start, restarted)

    def test_cancel_is_read_only_and_tampered_or_expired_tokens_cannot_reset(self):
        initial = self.timer.start
        response = self.client.post(self.url)
        token = response.context["confirmation"]
        self.client.get(reverse("core:timer-detail", args=[self.timer.pk]))
        self.client.post(self.url, {"confirmation": token + "bad"})
        with patch(
            "django.core.signing.time.time",
            return_value=timezone.now().timestamp() + 601,
        ):
            self.client.post(self.url, {"confirmation": token})
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.start, initial)

    def test_other_caregiver_change_invalidates_confirmation(self):
        token = self.client.post(self.url).context["confirmation"]
        self.timer.pause()
        paused = self.timer.paused_at
        response = self.client.post(self.url, {"confirmation": token})
        self.assertContains(response, "Review it before restarting.")
        self.timer.refresh_from_db()
        self.assertEqual(self.timer.paused_at, paused)

    def test_deleted_timer_views_and_stale_actions_are_friendly(self):
        pk = self.timer.pk
        token = self.client.post(self.url).context["confirmation"]
        self.timer.delete()
        for name, method in (
            ("detail", "get"),
            ("update", "get"),
            ("delete", "get"),
            ("pause", "post"),
            ("resume", "post"),
            ("restart", "post"),
        ):
            with self.subTest(name=name):
                response = getattr(self.client, method)(
                    reverse("core:timer-" + name, args=[pk]),
                    {"confirmation": token},
                    follow=True,
                )
                self.assertContains(response, "This timer is no longer available.")

    def test_restricted_user_cannot_restart_another_childs_timer(self):
        user = get_user_model().objects.create_user("restricted")
        user.user_permissions.add(Permission.objects.get(codename="change_timer"))
        user.settings.restrict_children = True
        user.settings.save()
        token = self.client.post(self.url).context["confirmation"]
        self.client.force_login(user)
        response = self.client.post(self.url, {"confirmation": token})
        self.assertEqual(response.status_code, 302)
        original = self.timer.start
        self.timer.refresh_from_db()
        self.assertEqual(original, self.timer.start)

    def test_dashboard_timer_duration_and_child_title(self):
        response = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        self.assertContains(response, "Timer (Test Baby)")
        self.assertContains(response, "45 minutes")
        self.assertNotContains(response, f"Timer #{self.timer.pk}")
        self.timer.context = {"activity": "sleep"}
        self.assertEqual(str(self.timer), "Sleep")

    def test_invalid_entry_has_linked_errors_and_preserves_values(self):
        response = self.client.post(
            reverse("core:weight-add"),
            {
                "child": self.child.pk,
                "date": "2020-01-02",
                "weight": "not a number",
                "entry_unit": "kg",
                "notes": "Keep these notes <safe>",
            },
        )
        self.assertContains(response, "data-form-errors")
        self.assertContains(response, 'href="#id_weight"')
        self.assertContains(response, "Keep these notes &lt;safe&gt;")
        self.assertContains(response, 'value="not a number"')
        self.assertFalse(models.Weight.objects.exists())

    def test_german_care_labels_and_elapsed_time(self):
        with translation.override("de"):
            self.assertEqual(translation.gettext("Solid"), "Stuhlgang")
            self.assertEqual(translation.gettext("Save"), "Speichern")
            self.assertEqual(
                translation.gettext("%(time_ago)s ago") % {"time_ago": "2 Stunden"},
                "vor 2 Stunden",
            )

    def test_timer_title_is_visible_on_each_supported_entry_form(self):
        self.timer.name = "Evening care"
        self.timer.save()
        for activity in ("feeding", "sleep", "pumping", "tummytime", "bathtime"):
            with self.subTest(activity=activity):
                response = self.client.get(
                    reverse("core:" + activity + "-add"), {"timer": self.timer.pk}
                )
                self.assertContains(response, 'name="timer"')
                self.assertContains(response, 'value="Evening care (Test Baby)"')
                self.assertTrue(response.context["form"].fields["timer"].disabled)
