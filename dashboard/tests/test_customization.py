from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from babybuddy.models import default_hidden_dashboard_cards
from core.models import Child


class DashboardCustomizationTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "dashboard-editor", is_superuser=True
        )
        self.other = get_user_model().objects.create_user(
            "other-dashboard", is_superuser=True
        )
        self.child = Child.objects.create(first_name="Alice", birth_date="2020-01-01")
        self.client.force_login(self.user)
        self.url = reverse("dashboard:dashboard-customize")
        self.dashboard = reverse("dashboard:dashboard-child", args=[self.child.slug])

    def test_defaults_custom_selection_reset_and_account_isolation(self):
        response = self.client.get(self.dashboard)
        self.assertEqual(
            response.context["dashboard_sections"][0]["panels"],
            [
                "feeding_last",
                "diaperchange_last",
                "sleep_last",
                "timer_list",
                "appointments_upcoming",
            ],
        )
        self.assertEqual(len(response.context["dashboard_sections"]), 1)
        self.assertContains(response, "Edit dashboard")
        self.assertNotContains(response, 'data-dashboard-panel="statistics"')
        response = self.client.post(
            self.url,
            {
                "care": ["pumping_last", "medication_last"],
                "trends": ["statistics"],
                "measurements": ["measurement_bmi"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.settings.refresh_from_db()
        self.assertNotIn("measurement_bmi", self.user.settings.dashboard_hidden_cards)
        self.assertIn("feeding_last", self.user.settings.dashboard_hidden_cards)
        self.other.settings.refresh_from_db()
        self.assertEqual(
            self.other.settings.dashboard_hidden_cards, default_hidden_dashboard_cards()
        )
        response = self.client.get(self.dashboard)
        self.assertContains(response, 'data-dashboard-panel="statistics"')
        self.assertNotContains(response, 'data-dashboard-panel="feeding_last"')
        self.client.post(self.url, {"action": "reset"})
        self.user.settings.refresh_from_db()
        self.assertEqual(
            self.user.settings.dashboard_hidden_cards, default_hidden_dashboard_cards()
        )

    def test_empty_selection_and_permissions(self):
        self.client.post(self.url, {})
        response = self.client.get(self.dashboard)
        self.assertEqual(response.context["dashboard_sections"], [])
        self.assertNotContains(response, 'class="dash-hero-measurements"')
        restricted = get_user_model().objects.create_user("restricted-dashboard")
        restricted.user_permissions.add(
            Permission.objects.get(
                codename="view_child", content_type__app_label="core"
            )
        )
        self.client.force_login(restricted)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'value="medication_last"')
        response = self.client.post(self.url, {"care": ["medication_last"]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
