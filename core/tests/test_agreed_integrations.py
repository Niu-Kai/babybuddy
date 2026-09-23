import datetime
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from core import models
from inventory.models import StockItem


class AgreedIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser(
            "integrationreview", "", "test-only"
        )
        self.child = models.Child.objects.create(
            first_name="Meal",
            last_name="Baby",
            birth_date=timezone.localdate() - datetime.timedelta(days=200),
        )
        self.other = models.Child.objects.create(
            first_name="Other", last_name="Baby", birth_date=self.child.birth_date
        )
        self.when = timezone.now() - datetime.timedelta(hours=2)
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.client.force_login(self.user)

    def meal(self, **kwargs):
        return {
            "child": self.child.pk,
            "start": self.when.isoformat(),
            "end": self.when.isoformat(),
            "type": "solid food",
            "method": "parent fed",
            **kwargs,
        }

    def create_meal(self):
        response = self.api.post(
            "/api/feedings/",
            self.meal(
                foods=[{"name": "Banana", "reaction": "liked"}, {"name": "Oatmeal"}]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_linked_foods_create_edit_and_time_sync(self):
        meal = self.create_meal()
        rows = meal["foods"]
        rows[0]["reaction"] = "neutral"
        later = self.when + datetime.timedelta(minutes=10)
        response = self.api.patch(
            f"/api/feedings/{meal['id']}/",
            {"foods": rows, "start": later.isoformat(), "end": later.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(models.Food.objects.count(), 2)
        self.assertTrue(all(food.time == later for food in models.Food.objects.all()))
        response = self.api.patch(
            f"/api/food/{rows[0]['id']}/", {"reaction": "disliked"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            self.api.get(f"/api/feedings/{meal['id']}/").data["foods"][0]["reaction"],
            "disliked",
        )
        response = self.api.patch(
            f"/api/food/{rows[0]['id']}/", {"child": self.other.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_removing_food_only_removes_that_exposure(self):
        meal = self.create_meal()
        response = self.api.patch(
            f"/api/feedings/{meal['id']}/", {"foods": meal["foods"][:1]}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(models.Food.objects.count(), 1)
        # Removing a meal preserves the existing food history as independent records.
        self.api.delete(f"/api/feedings/{meal['id']}/")
        self.assertIsNone(models.Food.objects.get().feeding_id)

    def test_food_ids_cannot_be_attached_to_another_meal(self):
        meal = self.create_meal()
        response = self.api.post(
            "/api/feedings/", self.meal(foods=meal["foods"]), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(models.Feeding.objects.count(), 1)
        response = self.api.patch(
            f"/api/feedings/{meal['id']}/",
            {"type": "formula", "method": "bottle"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_browser_meal_suggestions_and_save(self):
        meal = self.create_meal()
        url = reverse("core:feeding-update", args=[meal["id"]])
        response = self.client.get(url)
        self.assertContains(response, 'value="Banana"')
        self.assertContains(response, "Add food")
        data = self.meal()
        data.update(
            {
                "foods_name": ["Banana", "Oatmeal"],
                "foods_id": [row["id"] for row in meal["foods"]],
                "foods_reaction": ["liked", "neutral"],
            }
        )
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            302,
            response.context["form"].errors if response.status_code == 200 else "",
        )
        self.assertEqual(models.Food.objects.count(), 2)
        self.assertEqual(models.Food.objects.get(name="Oatmeal").reaction, "neutral")

    def test_settings_are_read_only_and_do_not_expose_secrets(self):
        response = self.api.get("/api/settings")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            set(response.data),
            {"timezone", "server_time", "sleep", "dashboard", "feeding"},
        )
        self.assertEqual(
            self.api.post("/api/settings", {}, format="json").status_code, 405
        )
        self.api.force_authenticate(None)
        self.assertIn(self.api.get("/api/settings").status_code, (401, 403))

    def query(self, queries):
        return self.api.post("/api/query", {"queries": queries}, format="json")

    def test_flexible_queries_filter_project_count_and_sum(self):
        self.create_meal()
        models.Sleep.objects.create(
            child=self.child,
            start=self.when - datetime.timedelta(hours=1),
            end=self.when,
        )
        stock = StockItem.objects.create(
            name="Shared diapers", category="diapers", quantity=80
        )
        response = self.query(
            [
                {
                    "key": "meal",
                    "resource": "feedings",
                    "filters": {"child": self.child.pk},
                    "fields": ["id", "foods"],
                    "limit": 1,
                },
                {
                    "key": "sleep",
                    "resource": "sleep",
                    "filters": {
                        "child": self.child.pk,
                        "start_min": (
                            self.when - datetime.timedelta(days=1)
                        ).isoformat(),
                    },
                    "operation": "sum",
                    "metric": "duration",
                },
                {"key": "count", "resource": "food", "operation": "count"},
                {
                    "key": "stock",
                    "resource": "inventory",
                    "filters": {"id": stock.pk},
                    "fields": ["quantity"],
                },
            ]
        )
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data["results"]
        self.assertEqual(set(result["meal"]["items"][0]), {"id", "foods"})
        self.assertEqual(result["sleep"], {"value": 3600, "unit": "seconds"})
        self.assertEqual(result["count"]["count"], 2)
        self.assertEqual(float(result["stock"]["items"][0]["quantity"]), 80)
        self.assertEqual(self.api.get("/api/query").status_code, 200)

    def test_query_validation_limits_and_pagination(self):
        self.create_meal()
        for extra in (
            {"limit": 51},
            {"filters": {"child__password": "x"}},
            {"fields": ["child__password"]},
            {"order_by": "child__password"},
            {"operation": "sum", "metric": "amount"},
            {"unknown": True},
        ):
            response = self.query([{"key": "q", "resource": "food", **extra}])
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            self.query([{"key": "q", "resource": "food"}] * 11).status_code, 400
        )
        self.assertEqual(
            self.query([{"key": "q", "resource": "food"}] * 2).status_code, 400
        )
        response = self.query([{"key": "q", "resource": "food", "limit": 1}])
        self.assertEqual(response.data["results"]["q"]["next_offset"], 1)

    def test_restricted_access_applies_to_queries_and_food_suggestions(self):
        self.create_meal()
        models.Food.objects.create(
            child=self.other, time=self.when, name="Private food"
        )
        user = get_user_model().objects.create_user("limitedintegration")
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "view_feeding",
                    "change_feeding",
                    "view_food",
                    "view_child",
                    "view_stockitem",
                    "view_sleep",
                ]
            )
        )
        user.settings.restrict_children = True
        user.settings.save()
        user.settings.allowed_children.set([self.child])
        self.api.force_authenticate(user)
        response = self.query([{"key": "q", "resource": "food", "operation": "count"}])
        self.assertEqual(response.data["results"]["q"]["count"], 2)
        response = self.query([{"key": "q", "resource": "notes"}])
        self.assertEqual(response.status_code, 403)
        self.client.force_login(user)
        response = self.client.get(
            reverse("core:feeding-update", args=[models.Feeding.objects.get().pk])
        )
        self.assertNotContains(response, "Private food")
        response = self.api.patch(
            f"/api/feedings/{models.Feeding.objects.get().pk}/",
            {"foods": []},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(models.Food.objects.count(), 3)

    def test_home_assistant_style_timestamps_preserve_same_instant(self):
        now = timezone.now()
        for offset in (0, -10, 5.5, 14):
            with self.subTest(offset=offset), patch(
                "django.utils.timezone.now", return_value=now
            ):
                instant = (now - datetime.timedelta(seconds=1)).astimezone(
                    datetime.timezone(datetime.timedelta(hours=offset))
                )
                # Home Assistant sends form-encoded aware datetimes.
                response = self.api.post(
                    "/api/feedings/",
                    self.meal(
                        type="formula",
                        method="bottle",
                        start=str(instant),
                        end=str(instant),
                    ),
                    format="multipart",
                )
                self.assertEqual(response.status_code, 201, response.data)
                entry = models.Feeding.objects.get(pk=response.data["id"])
                self.assertEqual(entry.start, now - datetime.timedelta(seconds=1))

    def test_current_time_accepted_and_future_clock_rejected(self):
        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            response = self.api.post(
                "/api/feedings/",
                self.meal(start=now.isoformat(), end=now.isoformat()),
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            for seconds in (1, 60, 3600):
                future = (now + datetime.timedelta(seconds=seconds)).isoformat()
                self.assertEqual(
                    self.api.post(
                        "/api/feedings/",
                        self.meal(start=future, end=future),
                        format="json",
                    ).status_code,
                    400,
                )
            response = self.api.post(
                "/api/feedings/",
                self.meal(
                    start=now.isoformat(),
                    end=(now + datetime.timedelta(minutes=5)).isoformat(),
                ),
                format="json",
            )
            self.assertEqual(response.status_code, 400)

    def test_timeline_groups_meal_foods_but_food_filter_still_shows_them(self):
        from core.timeline import get_objects

        self.create_meal()
        events = get_objects(child=self.child, user=self.user)
        self.assertEqual(len(events), 1)
        self.assertIn("Banana · Liked it", events[0]["details"])
        foods = get_objects(child=self.child, user=self.user, activity="food")
        self.assertEqual(len(foods), 2)

    def test_invalid_meal_form_preserves_food_rows(self):
        data = self.meal(method="bottle")
        data.update(
            {"foods_name": ["Banana"], "foods_reaction": ["liked"], "foods_id": [""]}
        )
        response = self.client.post(reverse("core:feeding-add"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Banana"')
        self.assertEqual(models.Food.objects.count(), 0)
