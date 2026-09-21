from datetime import datetime, timedelta, timezone as tz
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core import models
from reports import graphs


class UIConsistencyTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "ui-review", is_superuser=True, is_staff=True
        )
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Alice", birth_date="2020-01-01"
        )
        self.start = datetime(2024, 1, 1, 10, tzinfo=tz.utc)

    def test_tag_counts_filters_and_permissions(self):
        tag = models.Tag.objects.create(name="Checkup", color="#123456")
        for n in range(2):
            feed = models.Feeding.objects.create(
                child=self.child,
                start=self.start + timedelta(hours=n),
                end=self.start + timedelta(hours=n),
                type="formula",
                method="bottle",
            )
            feed.tags.add(tag)
            height = models.Height.objects.create(
                child=self.child, date="2024-01-01", height=50 + n, entry_unit="cm"
            )
            height.tags.add(tag)
        response = self.client.get(reverse("core:tag-detail", args=[tag.slug]))
        entries = {
            entry["label"]: entry
            for section in response.context["tag_sections"]
            for entry in section["entries"]
        }
        self.assertEqual(entries["Feedings"]["count"], 2)
        self.assertEqual(entries["Height"]["count"], 2)
        response = self.client.get(entries["Feedings"]["url"])
        self.assertEqual(response.context["filter"].qs.count(), 2)
        restricted = get_user_model().objects.create_user("tag-editor")
        restricted.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core", codename__in=["view_tag", "add_tag"]
            )
        )
        self.client.force_login(restricted)
        self.assertContains(self.client.get(reverse("core:tag-list")), "Add Tag")
        self.assertEqual(
            self.client.get(reverse("core:tag-detail", args=[tag.slug])).context[
                "tag_sections"
            ],
            [],
        )

    def test_data_age_preference_and_modern_child_history(self):
        self.user.settings.dashboard_hide_age = timedelta(days=1)
        self.user.settings.save(update_fields=["dashboard_hide_age"])
        response = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        self.assertContains(response, "icon-clock")
        self.assertContains(response, "Born")
        response = self.client.get(
            reverse("core:child", args=[self.child.slug]),
            {"period": "month", "date": "invalid"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["timeline_filter"].errors)
        self.assertContains(response, "data-timeline-filters")

    def test_management_pages_and_entry_controls(self):
        for route in ("core:child-list", "core:tag-list", "babybuddy:user-list"):
            response = self.client.get(reverse(route))
            self.assertNotContains(response, 'name="from"')
            self.assertNotContains(response, "table-striped")
            self.assertContains(response, "record-table")
        for name in (
            "feeding",
            "sleep",
            "pumping",
            "diaperchange",
            "medication",
            "note",
            "temperature",
            "tummytime",
            "bathtime",
            "food",
            "reflux",
            "timer",
            "weight",
            "height",
            "head-circumference",
            "appointment",
            "child",
            "tag",
        ):
            with self.subTest(form=name):
                response = self.client.get(reverse("core:" + name + "-add"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'type="datetime-local"')
                self.assertNotContains(response, 'class="help-block"')
        settings = self.client.get(reverse("babybuddy:user-settings"))
        self.assertNotContains(settings, 'name="dashboard_cards_present"')
        self.assertContains(settings, "Edit dashboard")

    def test_interval_charts_handle_single_and_duplicate_times(self):
        for model, graph, time_field, extra in (
            (
                models.Feeding,
                graphs.feeding_intervals,
                "start",
                {"type": "formula", "method": "bottle"},
            ),
            (
                models.Medication,
                graphs.medication_intervals,
                "time",
                {"name": "Vitamin"},
            ),
            (
                models.DiaperChange,
                graphs.diaperchange_intervals,
                "time",
                {"wet": True, "solid": False},
            ),
        ):
            with self.subTest(model=model):
                first = model.objects.create(
                    child=self.child, **{time_field: self.start}, **extra
                )
                queryset = model.objects.filter(child=self.child)
                self.assertEqual(graph(queryset), (None, None))
                model.objects.create(
                    child=self.child, **{time_field: self.start}, **extra
                )
                model.objects.create(
                    child=self.child,
                    **{time_field: self.start + timedelta(hours=3)},
                    **extra
                )
                with patch(
                    "plotly.offline.plot",
                    return_value="<div><script>chart()</script></div>",
                ) as plot:
                    graph(queryset)
                traces = plot.call_args.args[0].data
                for trace in traces:
                    self.assertEqual(len(trace.x), len(trace.y))
                    if len(trace.x):
                        self.assertEqual(
                            list(trace.x), [self.start + timedelta(hours=3)]
                        )
                        self.assertEqual(list(trace.y), [3.0])

    def test_account_expiration_has_separate_optional_controls(self):
        response = self.client.get(
            reverse("babybuddy:user-update", args=[self.user.pk])
        )
        self.assertContains(response, 'name="access_expires_0"')
        self.assertContains(response, 'name="access_expires_1"')
        self.assertNotContains(response, 'type="datetime-local"')
        field = response.context["form"].fields["access_expires"]
        self.assertIsNone(field.clean(["", ""]))
        self.assertEqual(field.clean(["2027-01-02", "1:30 PM"]).hour, 13)
        self.assertEqual(field.clean(["2027-01-02", "13:30"]).minute, 30)
