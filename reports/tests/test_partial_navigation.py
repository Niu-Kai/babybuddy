from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from core.models import Child, Weight
from reports.utils import plot_payloads


class PartialNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "report-nav", is_superuser=True
        )
        self.child = Child.objects.create(first_name="Sam", birth_date=date(2024, 1, 1))
        self.other = Child.objects.create(
            first_name="Alex", birth_date=date(2024, 1, 1)
        )
        for child in (self.child, self.other):
            Weight.objects.create(
                child=child, date=date(2024, 1, 2), weight=4, entry_unit="kg"
            )
        self.client.force_login(self.user)

    def partial(self, url, query=None):
        return self.client.get(url, query or {}, HTTP_X_REPORT_PARTIAL="1")

    def test_report_index_and_chart_payload_keep_full_page_fallback(self):
        url = reverse("reports:growth", args=[self.child.slug])
        response = self.partial(url, {"scope": self.child.slug, "metric": "weight"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertEqual(len(data["plots"]), 1)
        self.assertNotIn("<script", data["html"])
        self.assertNotIn('<nav class="navbar', data["html"])
        self.assertIn(data["plots"][0]["id"], data["html"])
        self.assertEqual(data["plots"][0]["data"][0]["name"], "Sam")
        self.assertIn("data-report-page", data["html"])
        self.assertIn("data-timeline-filters", data["html"])
        self.assertContains(self.client.get(url), "Plotly.newPlot")
        index = self.partial(reverse("reports:home")).json()
        self.assertEqual(index["plots"], [])
        self.assertIn("report-categories", index["html"])

    def test_comparison_returns_independent_charts(self):
        url = reverse("reports:growth", args=[self.child.slug])
        data = self.partial(url, {"scope": "compare"}).json()
        self.assertEqual(len(data["plots"]), 2)
        self.assertEqual(len({plot["id"] for plot in data["plots"]}), 2)
        self.assertEqual(
            {plot["data"][0]["name"] for plot in data["plots"]}, {"Sam", "Alex"}
        )

    def test_partial_requests_enforce_permissions(self):
        url = reverse("reports:growth", args=[self.child.slug])
        self.assertEqual(Client().get(url, HTTP_X_REPORT_PARTIAL="1").status_code, 302)
        limited = get_user_model().objects.create_user("no-reports")
        self.client.force_login(limited)
        self.assertEqual(self.partial(url).status_code, 403)

    def test_empty_chart_has_no_initializers(self):
        Weight.objects.all().delete()
        url = reverse("reports:growth", args=[self.child.slug])
        data = self.partial(url, {"scope": self.child.slug}).json()
        self.assertEqual(data["plots"], [])
        self.assertIn("report-empty-state", data["html"])

    def test_plot_payload_parser_handles_data_that_looks_like_code(self):
        import json

        label = "Plotly.newPlot( <script>alert(1)</script>"
        script = 'Plotly.newPlot("chart",' + json.dumps([{"name": label}]) + ",{},{});"
        plots = plot_payloads(script)
        self.assertEqual(len(plots), 1)
        self.assertEqual(plots[0]["data"][0]["name"], label)
