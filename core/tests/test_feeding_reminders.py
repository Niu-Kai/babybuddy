from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.feeding_reminders import age_suggestion, reminders_for
from core.models import Child, Feeding, FeedingReminder, Timer


class FeedingReminderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "reminder-parent", "", "test"
        )
        self.other = get_user_model().objects.create_superuser(
            "other-parent", "", "test"
        )
        self.child = Child.objects.create(
            first_name="Newborn", birth_date=timezone.localdate() - timedelta(days=3)
        )
        self.sibling = Child.objects.create(
            first_name="Sibling", birth_date=timezone.localdate() - timedelta(days=40)
        )
        self.client.force_login(self.user)
        self.now = timezone.now()
        self.plan = FeedingReminder.objects.create(
            user=self.user, child=self.child, enabled=True
        )

    def feed(self, child=None, **kwargs):
        return Feeding.objects.create(
            child=child or self.child,
            start=kwargs.pop("start", self.now - timedelta(hours=3)),
            end=kwargs.pop("end", self.now - timedelta(hours=3)),
            type=kwargs.pop("type", "breast milk"),
            method="bottle",
            **kwargs,
        )

    def test_newborn_reminder_changes_with_age_and_milk(self):
        day = self.child.birth_date
        self.assertEqual(age_suggestion(self.child, "mixed", day)[0], 150)
        self.assertEqual(
            age_suggestion(self.child, "formula", day + timedelta(days=10))[0], 210
        )
        self.assertEqual(
            age_suggestion(self.child, "breast", day + timedelta(days=40))[0], 180
        )
        self.assertIsNone(
            age_suggestion(self.child, "breast", day + timedelta(days=200))[0]
        )
        self.assertIsNone(
            age_suggestion(self.child, "breast", day - timedelta(days=1))[0]
        )
        self.child.due_date = day + timedelta(days=35)
        self.assertIsNone(
            age_suggestion(self.child, "breast", day + timedelta(days=40))[0]
        )

    def test_alarm_is_per_child_and_any_caregivers_milk_feed_resets_it(self):
        self.feed()
        FeedingReminder.objects.create(user=self.user, child=self.sibling, enabled=True)
        self.feed(
            self.sibling,
            start=self.now - timedelta(minutes=10),
            end=self.now - timedelta(minutes=10),
        )
        rows = {row["child"].pk: row for row in reminders_for(self.user)}
        self.assertTrue(rows[self.child.pk]["ready"])
        self.assertFalse(rows[self.sibling.pk]["ready"])
        self.feed(
            created_by=self.other,
            start=self.now - timedelta(minutes=1),
            end=self.now - timedelta(minutes=1),
        )
        self.assertFalse(next(reminders_for(self.user))["ready"])

    def test_solids_do_not_reset_milk_clock_and_topup_uses_its_own_start(self):
        first = self.feed()
        self.feed(
            type="solid food",
            start=self.now - timedelta(minutes=2),
            end=self.now - timedelta(minutes=2),
        )
        row = next(reminders_for(self.user))
        self.assertTrue(row["ready"])
        self.assertEqual(row["count"], 1)
        first.top_up_at = self.now - timedelta(minutes=10)
        first.top_up_type = "formula"
        first.top_up_amount = 20
        first.save()
        row = next(reminders_for(self.user))
        self.assertEqual(row["reference"], first.top_up_at)
        self.assertEqual(row["count"], 1)
        self.assertFalse(row["ready"])

    def test_no_first_feed_no_alarm_and_running_timer_suppresses_alarm(self):
        self.assertIsNone(next(reminders_for(self.user))["due"])
        self.feed()
        Timer.objects.create(
            user=self.other, child=self.child, context={"activity": "feeding"}
        )
        row = next(reminders_for(self.user))
        self.assertTrue(row["active"])
        self.assertFalse(row["ready"])

    def test_snooze_then_new_feed_ignores_old_snooze(self):
        self.feed()
        url = reverse("core:feeding-reminder-status")
        response = self.client.post(url, {"id": self.plan.pk})
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertGreater(self.plan.snoozed_until, self.now)
        self.assertFalse(next(reminders_for(self.user))["ready"])
        new = self.feed(
            start=self.now - timedelta(minutes=1), end=self.now - timedelta(minutes=1)
        )
        self.assertEqual(
            next(reminders_for(self.user))["due"], new.start + timedelta(minutes=150)
        )

    def test_settings_are_personal_validated_and_persisted(self):
        url = reverse("core:feeding-reminders")
        prefix = str(self.child.pk) + "-"
        data = {
            "child": self.child.pk,
            prefix + "enabled": "on",
            prefix + "mode": "custom",
            prefix + "milk": "mixed",
        }
        self.assertEqual(self.client.post(url, data).status_code, 200)
        data[prefix + "minutes"] = 120
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.minutes, 120)
        self.assertFalse(FeedingReminder.objects.filter(user=self.other).exists())
        self.assertContains(self.client.get(url), "data-enable-feeding-alerts")
        self.assertEqual(self.client.post(url, {"child": "invalid"}).status_code, 404)

    def test_restricted_user_sees_only_allowed_children_and_cannot_snooze_others(self):
        viewer = get_user_model().objects.create_user("limited-reminders")
        viewer.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_child", "view_feeding"])
        )
        viewer.settings.restrict_children = True
        viewer.settings.save()
        viewer.settings.allowed_children.add(self.sibling)
        FeedingReminder.objects.create(user=viewer, child=self.sibling, enabled=True)
        self.client.force_login(viewer)
        response = self.client.get(reverse("core:feeding-reminders"))
        self.assertContains(response, "Sibling")
        self.assertNotContains(response, "Newborn")
        self.assertEqual(
            self.client.post(
                reverse("core:feeding-reminders"), {"child": self.child.pk}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("core:feeding-reminder-status"), {"id": self.plan.pk}
            ).status_code,
            404,
        )
        data = self.client.get(reverse("core:feeding-reminder-status")).json()
        self.assertEqual(len(data["reminders"]), 1)
        self.assertEqual(data["reminders"][0]["child"], "Sibling")

    def test_write_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                reverse("core:feeding-reminder-status"), {"id": self.plan.pk}
            ).status_code,
            403,
        )

    def test_age_transition_prompts_review_instead_of_silently_removing_reminder(self):
        self.child.birth_date = timezone.localdate() - timedelta(days=200)
        self.child.save()
        data = self.client.get(reverse("core:feeding-reminder-status")).json()
        row = data["reminders"][0]
        self.assertTrue(row["review"])
        self.assertFalse(row["ready"])
        self.assertIn("?scope=" + self.child.slug, row["url"])
