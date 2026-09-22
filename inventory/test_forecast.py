from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from core.models import Child, DiaperChange
from .forecast import daily_rates, forecast_items
from .forms import ItemForm
from .models import ChildSupplyProfile, StockItem, StockMovement


class AutomaticReminderTests(TestCase):
    def setUp(self):
        self.child = Child.objects.create(
            first_name="Sam", birth_date=timezone.localdate() - timedelta(days=60)
        )
        self.item = StockItem.objects.create(
            name="Shared diapers",
            category="diapers",
            unit="diapers",
            size="Newborn",
            quantity=112,
        )
        self.profile = ChildSupplyProfile.objects.create(
            child=self.child, diaper_stock=self.item
        )

    def at_day(self, days_ago, hour=12):
        return timezone.make_aware(
            datetime.combine(
                timezone.localdate() - timedelta(days=days_ago), time(hour)
            )
        )

    def logs(self, child, count, days_ago):
        DiaperChange.objects.bulk_create(
            [
                DiaperChange(
                    child=child, wet=True, solid=True, time=self.at_day(days_ago)
                )
                for _ in range(count)
            ]
        )

    def rate(self, item=None):
        item = item or self.item
        return daily_rates(StockItem.objects.all())[item.pk]

    def test_fourteen_day_boundary_and_restock_clears_reminder(self):
        for day in range(1, 15):
            self.logs(self.child, 8, day)
        self.assertEqual(self.rate(), 8)
        self.assertEqual(self.item.days_left, 14)
        self.assertEqual(self.item.reminder, "Running low")
        self.assertEqual(self.item.buy_quantity, 240)
        self.item.quantity = Decimal(113)
        self.assertEqual(self.item.days_left, 15)
        self.assertEqual(self.item.reminder, "")
        self.item.quantity = 480
        self.assertEqual(self.item.days_left, 60)
        self.assertEqual(self.item.reminder, "")
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 112)  # Forecasting never writes stock.
        self.assertFalse(StockMovement.objects.exists())

    def test_combines_children_with_different_logging_start_dates(self):
        other = Child.objects.create(
            first_name="Alex", birth_date=self.child.birth_date
        )
        ChildSupplyProfile.objects.create(child=other, diaper_stock=self.item)
        for day in range(1, 15):
            self.logs(self.child, 8, day)
        for day in range(1, 4):
            self.logs(other, 6, day)
        self.assertEqual(self.rate(), 14)
        self.assertEqual(self.item.days_left, 8)

    def test_usage_follows_child_to_larger_supply(self):
        self.logs(self.child, 8, 1)
        larger = StockItem.objects.create(
            name="Larger",
            category="diapers",
            unit="diapers",
            size="Bigger",
            quantity=112,
            min_age_months=6,
        )
        self.profile.diaper_stock = larger
        self.profile.save()
        self.assertEqual(self.rate(larger), 8)
        self.assertIsNone(self.rate(self.item))
        self.assertEqual(larger.reminder, "Running low")
        self.assertEqual(self.item.reminder, "")

    def test_automatic_age_matching_and_ambiguity_use_consumption_rules(self):
        self.profile.delete()
        self.item.max_age_months = 3
        self.item.save()
        self.logs(self.child, 8, 1)
        self.assertEqual(self.rate(), 8)
        StockItem.objects.create(
            name="Another", category="diapers", unit="diapers", max_age_months=3
        )
        self.assertIsNone(self.rate())

    def test_no_recent_or_only_partial_day_data_does_not_guess(self):
        self.assertIsNone(self.rate())
        self.logs(self.child, 80, 15)
        self.logs(self.child, 3, 0)
        self.logs(self.child, 100, -1)
        self.assertIsNone(self.rate())
        self.assertIsNone(self.item.days_left)
        self.assertEqual(self.item.reminder, "")
        self.item.quantity = 0
        self.assertEqual(self.item.reminder, "Out of stock")

    def test_missing_history_for_one_shared_child_does_not_underestimate(self):
        self.logs(self.child, 8, 1)
        other = Child.objects.create(
            first_name="Alex", birth_date=self.child.birth_date
        )
        ChildSupplyProfile.objects.create(child=other, diaper_stock=self.item)
        self.assertIsNone(self.rate())

    def test_zero_use_days_are_included_and_old_logs_ignored(self):
        self.logs(self.child, 80, 15)
        self.logs(self.child, 8, 4)
        self.logs(self.child, 8, 1)
        self.logs(self.child, 100, 0)
        self.assertEqual(self.rate(), 4)

    def test_entry_edit_and_delete_update_rate_without_double_counting(self):
        self.logs(self.child, 8, 1)
        entry = DiaperChange.objects.first()
        entry.notes = "Edited"
        entry.save()
        self.assertEqual(self.rate(), 8)
        entry.delete()
        self.assertEqual(self.rate(), 7)

    def test_other_items_use_only_explicit_use_movements(self):
        item = StockItem.objects.create(
            name="Wipes", category="wipes", unit="wipes", quantity=28
        )
        for day in (1, 2):
            StockMovement.objects.create(
                item=item,
                action="use",
                change=-2,
                balance=60,
                created_at=self.at_day(day),
            )
        StockMovement.objects.create(
            item=item, action="add", change=100, balance=160, created_at=self.at_day(1)
        )
        StockMovement.objects.create(
            item=item, action="set", change=-50, balance=110, created_at=self.at_day(1)
        )
        self.assertEqual(self.rate(item), 2)
        self.assertEqual(item.days_left, 14)
        self.assertEqual(item.reminder, "Running low")

    def test_inactive_and_pack_inventory_do_not_get_diaper_forecasts(self):
        self.logs(self.child, 8, 1)
        for changes in ({"archived": True}, {"stage": "next"}, {"unit": "packs"}):
            with self.subTest(changes=changes):
                StockItem.objects.filter(pk=self.item.pk).update(**changes)
                self.assertIsNone(self.rate())
                StockItem.objects.filter(pk=self.item.pk).update(
                    archived=False, stage="current", unit="diapers"
                )

    def test_local_calendar_day_boundaries(self):
        with timezone.override(ZoneInfo("Pacific/Honolulu")):
            # 9 a.m. UTC is still yesterday in Hawaii, even if it's today in UTC.
            today = timezone.localdate()
            midnight = timezone.make_aware(datetime.combine(today, time.min))
            DiaperChange.objects.bulk_create(
                [
                    DiaperChange(
                        child=self.child,
                        wet=True,
                        solid=False,
                        time=midnight - timedelta(minutes=1),
                    ),
                    DiaperChange(
                        child=self.child, wet=True, solid=False, time=midnight
                    ),
                ]
            )
            self.assertEqual(self.rate(), 1)

    def test_automatic_fields_and_dashboard_shopping_list_are_consistent(self):
        user = get_user_model().objects.create_user("parent", is_superuser=True)
        self.client.force_login(user)
        self.logs(self.child, 8, 1)
        for field in ("low_stock", "target_stock", "daily_use", "reminder_days"):
            self.assertNotIn(field, ItemForm().fields)
        self.assertContains(
            self.client.get(reverse("dashboard:dashboard"), follow=True),
            "Supplies need attention",
        )
        self.assertContains(
            self.client.get(reverse("inventory:list"), {"view": "shopping"}),
            "Shared diapers",
        )
        detail = self.client.get(reverse("inventory:detail", args=[self.item.pk]))
        self.assertContains(detail, "14 days of stock remaining")
        self.assertContains(detail, "8 diapers/day")
        StockItem.objects.filter(pk=self.item.pk).update(quantity=480)
        self.assertNotContains(
            self.client.get(reverse("inventory:list"), {"view": "shopping"}),
            "Shared diapers",
        )

    def test_forecast_snapshot_has_bounded_queries_and_is_request_local(self):
        self.logs(self.child, 8, 1)
        request = RequestFactory().get("/inventory/")
        with self.assertNumQueries(3):
            items = forecast_items(request)
        with self.assertNumQueries(0):
            self.assertIs(forecast_items(request), items)
            self.assertEqual(items[0].days_left, 14)
            self.assertEqual(items[0].reminder, "Running low")
        self.logs(self.child, 2, 1)
        self.assertEqual(
            forecast_items(RequestFactory().get("/"))[0].daily_use_rate, 10
        )

    def test_expiration_reminders_begin_two_weeks_beforehand(self):
        self.item.expiration_date = timezone.localdate() + timedelta(days=15)
        self.assertEqual(self.item.reminder, "")
        self.item.expiration_date = timezone.localdate() + timedelta(days=14)
        self.assertEqual(self.item.reminder, "Expiring soon")

    def test_navigation_does_not_load_archived_inventory_or_notes(self):
        StockItem.objects.create(name="Archived", archived=True, notes="Large history")
        items = forecast_items(RequestFactory().get("/"))
        self.assertEqual([item.pk for item in items], [self.item.pk])
        self.assertIn("notes", items[0].get_deferred_fields())
