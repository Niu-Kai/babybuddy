from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from babybuddy.forms import UserSettingsForm
from core import models
from core.feature_preferences import activity_choices, OPTIONAL_FIELDS


class EntryPreferencesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "preferences", is_superuser=True
        )
        self.other = get_user_model().objects.create_user("other")
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Baby", birth_date=timezone.localdate()
        )
        self.activities = [key for key, _label in activity_choices()]
        self.fields = list(OPTIONAL_FIELDS)
        self.payload = {
            "language": "en-US",
            "theme": "dark",
            "timezone": "UTC",
            "pagination_count": 25,
            "dashboard_refresh_rate": "0:01:00",
            "entry_preferences_present": "1",
            "shown_activities": self.activities,
            "shown_entry_fields": self.fields,
        }

    def save_preferences(self, **changes):
        response = self.client.post(
            reverse("babybuddy:user-settings"), self.payload | changes
        )
        self.assertEqual(
            response.status_code,
            302,
            (
                response.context["form_settings"].errors
                if response.status_code == 200
                else "Unexpected redirect"
            ),
        )
        self.user.settings.refresh_from_db()

    def test_hide_save_reload_and_restore(self):
        self.save_preferences(
            shown_activities=[
                key for key in self.activities if key not in ("pumping", "height")
            ],
            shown_entry_fields=[key for key in self.fields if key != "notes"],
        )
        self.assertEqual(
            set(self.user.settings.hidden_activities), {"pumping", "height"}
        )
        self.assertEqual(self.user.settings.hidden_entry_fields, ["notes"])
        page = self.client.get(reverse("babybuddy:user-settings"))
        form = page.context["form_settings"]
        self.assertNotIn("pumping", form["shown_activities"].value())
        menus = (
            page.context["activity_menu"]
            + page.context["measurement_menu"]
            + page.context["add_menu"]
        )
        urls = [item["url"] for group in menus for item in group["items"]]
        self.assertNotIn(reverse("core:pumping-list"), urls)
        self.assertNotIn(reverse("core:pumping-add"), urls)
        self.assertNotIn(reverse("core:height-list"), urls)
        self.assertNotContains(page, 'class="form-select" id="id_shown_activities"')
        self.assertContains(
            page, 'type="checkbox" name="shown_activities"', count=len(self.activities)
        )
        entry = self.client.get(reverse("core:feeding-add"))
        self.assertTrue(entry.context["form"].fields["notes"].widget.is_hidden)
        self.other.settings.refresh_from_db()
        self.assertEqual(self.other.settings.hidden_activities, [])
        self.save_preferences()
        self.assertEqual(self.user.settings.hidden_activities, [])
        self.assertEqual(self.user.settings.hidden_entry_fields, [])
        entry = self.client.get(reverse("core:feeding-add"))
        self.assertFalse(entry.context["form"].fields["notes"].widget.is_hidden)

    def test_uncheck_all_then_show_all(self):
        self.save_preferences(shown_activities=[], shown_entry_fields=[])
        self.assertEqual(
            set(self.user.settings.hidden_activities), set(self.activities)
        )
        self.assertEqual(set(self.user.settings.hidden_entry_fields), set(self.fields))
        self.save_preferences()
        self.assertEqual(self.user.settings.hidden_activities, [])

    def test_missing_controls_and_invalid_submission_preserve_preferences(self):
        self.save_preferences(shown_entry_fields=[])
        payload = self.payload.copy()
        for key in (
            "entry_preferences_present",
            "shown_activities",
            "shown_entry_fields",
        ):
            payload.pop(key)
        form = UserSettingsForm(instance=self.user.settings, data=payload)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(set(self.user.settings.hidden_entry_fields), set(self.fields))
        response = self.client.post(
            reverse("babybuddy:user-settings"),
            self.payload | {"shown_activities": ["invalid"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("shown_activities", response.context["form_settings"].errors)
        self.user.settings.refresh_from_db()
        self.assertEqual(set(self.user.settings.hidden_entry_fields), set(self.fields))

    def test_hidden_fields_preserve_existing_entry_values(self):
        self.save_preferences(shown_entry_fields=[])
        start = timezone.now() - timedelta(hours=2)
        entry = models.Feeding.objects.create(
            child=self.child,
            start=start,
            end=start,
            type="formula",
            method="bottle",
            notes="Keep this note",
            amount=90,
            entry_unit="mL",
        )
        entry.tags.add("Keep tag")
        from core.forms import FeedingForm
        from core.feature_preferences import apply_fields

        form = FeedingForm(
            user=self.user,
            instance=entry,
            data={
                "child": self.child.pk,
                "start": start.isoformat(),
                "end": start.isoformat(),
                "type": "formula",
                "method": "bottle",
            },
        )
        apply_fields(form)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        entry.refresh_from_db()
        self.assertEqual(entry.notes, "Keep this note")
        self.assertEqual(entry.amount, 90)
        self.assertEqual(list(entry.tags.names()), ["Keep tag"])
