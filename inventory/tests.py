from datetime import timedelta
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from core.models import Child, DiaperChange
from .models import StockItem, StockMovement, ChildSupplyProfile
from .forms import ItemForm, MovementForm
from .apps import grant_inventory_permissions


class InventoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "inventory-parent", is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = Child.objects.create(
            first_name="Sam", birth_date=timezone.localdate() - timedelta(days=100)
        )
        self.other = Child.objects.create(
            first_name="Alex", birth_date=timezone.localdate() - timedelta(days=40)
        )
        self.item = StockItem.objects.create(
            name="Diapers",
            category="diapers",
            size="2",
            unit="diapers",
            quantity=20,
        )

    def change(self, action, amount, token=None):
        form = MovementForm(
            {"action": action, "amount": amount, "token": token or uuid.uuid4()},
            item=self.item,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.apply(self.user)
        self.item.refresh_from_db()
        return form

    def test_stock_updates_and_replay_are_safe(self):
        token = uuid.uuid4()
        self.change("use", 3, token)
        self.change("use", 3, token)
        self.assertEqual(self.item.quantity, 17)
        self.assertEqual(self.item.movements.count(), 1)
        self.change("add", 10)
        self.change("set", 5)
        self.assertEqual(self.item.quantity, 5)
        self.assertEqual(self.item.movements.first().change, -22)
        with self.assertRaises(ValidationError):
            self.change("use", 6)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_discrete_counts_and_invalid_thresholds(self):
        form = MovementForm(
            {"action": "use", "amount": "1.5", "token": uuid.uuid4()}, item=self.item
        )
        self.assertFalse(form.is_valid())
        self.item.min_age_months = 6
        self.item.max_age_months = 3
        with self.assertRaises(ValidationError):
            self.item.full_clean()

    def record_daily_use(self):
        ChildSupplyProfile.objects.create(child=self.child, diaper_stock=self.item)
        DiaperChange.objects.bulk_create(
            [
                DiaperChange(
                    child=self.child,
                    wet=True,
                    solid=False,
                    time=timezone.now() - timedelta(days=1),
                )
                for _ in range(8)
            ]
        )

    def test_reminders_forecast_and_snooze(self):
        self.record_daily_use()
        self.assertEqual(self.item.alert, "Running low")
        self.assertEqual(self.item.days_left, 3)
        self.assertEqual(self.item.buy_quantity, 240)
        self.item.snoozed_until = timezone.localdate() + timedelta(days=7)
        self.assertEqual(self.item.alert, "")
        self.assertEqual(self.item.reminder, "Running low")

    def test_child_growth_does_not_change_household_stage_or_quantity(self):
        ChildSupplyProfile.objects.create(child=self.child, diaper_size="3")
        self.item.min_age_months = 6
        self.item.max_age_months = 9
        self.item.save()
        self.assertEqual(self.item.fit, "current")
        self.assertEqual(self.item.quantity, 20)
        self.item.stage = "next"
        self.assertEqual(self.item.reminder, "")
        self.item.stage = "outgrown"
        self.assertEqual(self.item.reminder, "")

    def test_expiration(self):
        self.item.expiration_date = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self.item.reminder, "Expired")
        self.assertIsNone(self.item.buy_quantity)
        self.item.expiration_date = timezone.localdate() + timedelta(days=2)
        self.assertEqual(self.item.reminder, "Expiring soon")

    def test_all_stock_is_shared_regardless_of_child_scope(self):
        shared = StockItem.objects.create(name="Shared wipes", unit="packs", quantity=1)
        clothes = StockItem.objects.create(name="Clothes")
        for scope in (self.child.slug, self.other.slug, "compare", "all"):
            response = self.client.get(reverse("inventory:list"), {"scope": scope})
            self.assertEqual(
                {item.pk for item in response.context["items"]},
                {self.item.pk, shared.pk, clothes.pk},
            )
            self.assertTrue(response.context["household_page"])
            self.assertNotContains(response, 'class="inventory-size-bar"')
            self.assertNotContains(response, 'class="comparison-grid')
        self.assertNotIn("child", ItemForm().fields)
        self.assertNotContains(
            self.client.get(reverse("inventory:add")), 'for="id_child"'
        )
        self.assertContains(
            self.client.get(reverse("core:child-list")),
            reverse("inventory:sizes", args=[self.child.pk]),
        )

    def test_add_edit_and_history(self):
        data = {
            "name": "Wipes",
            "category": "wipes",
            "child": "",
            "size": "",
            "stage": "current",
            "unit": "packs",
            "starting_quantity": 4,
        }
        response = self.client.post(reverse("inventory:add"), data)
        self.assertEqual(response.status_code, 302)
        item = StockItem.objects.get(name="Wipes")
        self.assertEqual(item.quantity, 4)
        self.assertEqual(item.movements.first().balance, 4)
        data["unit"] = "g"
        data["quantity"] = 999
        response = self.client.post(reverse("inventory:edit", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.unit, "packs")
        self.assertEqual(item.quantity, 4)
        self.assertContains(
            self.client.get(reverse("inventory:detail", args=[item.pk])),
            "Starting stock",
        )

    def test_permissions_and_post_only_actions(self):
        restricted = get_user_model().objects.create_user("inventory-reader")
        restricted.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="inventory", codename="view_stockitem"
            ),
            *Permission.objects.filter(
                codename="view_child", content_type__app_label="core"
            )
        )
        self.client.force_login(restricted)
        self.assertEqual(self.client.get(reverse("inventory:list")).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("inventory:stock", args=[self.item.pk]), {}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("inventory:sizes", args=[self.child.pk])
            ).status_code,
            403,
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(
                reverse("inventory:action", args=[self.item.pk])
            ).status_code,
            405,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(
                reverse("inventory:action", args=[self.item.pk]), {"action": "archive"}
            ).status_code,
            403,
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse("inventory:list")).status_code, 302)

    def test_inventory_permission_is_enough_for_shared_stock(self):
        user = get_user_model().objects.create_user("shared-only")
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="inventory", codename="view_stockitem"
            )
        )
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(
                reverse("inventory:detail", args=[self.item.pk])
            ).status_code,
            200,
        )

    def test_archive_snooze_and_dashboard_reminder(self):
        self.record_daily_use()
        response = self.client.get(reverse("dashboard:dashboard"), {"scope": "all"})
        self.assertContains(response, "Supplies need attention")
        self.client.post(
            reverse("inventory:action", args=[self.item.pk]), {"action": "snooze"}
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.alert, "")
        self.assertContains(
            self.client.get(reverse("inventory:list"), {"view": "shopping"}), "Diapers"
        )
        self.client.post(
            reverse("inventory:action", args=[self.item.pk]), {"action": "archive"}
        )
        self.assertEqual(
            len(self.client.get(reverse("inventory:list")).context["items"]), 0
        )
        self.assertEqual(
            len(
                self.client.get(
                    reverse("inventory:list"), {"view": "archived"}
                ).context["items"]
            ),
            1,
        )
        with self.assertRaises(ValidationError):
            self.change("add", 1)

    def test_expired_batch_not_silently_combined_with_new_stock(self):
        self.item.expiration_date = timezone.localdate() - timedelta(days=1)
        self.item.save()
        with self.assertRaises(ValidationError):
            self.change("add", 10)
        self.change("set", 0)
        self.assertEqual(self.item.quantity, 0)
        with self.assertRaises(ValidationError):
            self.change("add", 1)

    def test_all_forms_render(self):
        for url in [
            reverse("inventory:add"),
            reverse("inventory:edit", args=[self.item.pk]),
            reverse("inventory:stock", args=[self.item.pk]),
            reverse("inventory:sizes", args=[self.child.pk]),
        ]:
            self.assertContains(self.client.get(url), "Cancel")
        self.assertFalse(ChildSupplyProfile.objects.exists())

    def test_group_permissions_include_inventory(self):
        from django.conf import settings

        group, _ = Group.objects.get_or_create(
            name=settings.BABY_BUDDY["CAREGIVER_GROUP_NAME"]
        )
        grant_inventory_permissions(None)
        codes = set(
            group.permissions.filter(content_type__app_label="inventory").values_list(
                "codename", flat=True
            )
        )
        self.assertIn("change_stockitem", codes)
        self.assertNotIn("delete_stockitem", codes)

    def test_deleting_child_preserves_stock_as_shared(self):
        self.child.delete()
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 20)
