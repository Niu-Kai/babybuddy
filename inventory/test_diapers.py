from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Child, DiaperChange
from .forms import SizeForm
from .models import ChildSupplyProfile, DiaperStockUsage, StockItem, StockMovement


class DiaperInventoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "diaper-parent", is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = Child.objects.create(
            first_name="Sam", birth_date=timezone.localdate() - timedelta(days=100)
        )
        self.other = Child.objects.create(
            first_name="Alex", birth_date=timezone.localdate() - timedelta(days=40)
        )
        self.profile = ChildSupplyProfile.objects.create(
            child=self.child, diaper_size="2"
        )
        self.other_profile = ChildSupplyProfile.objects.create(
            child=self.other, diaper_size="Newborn"
        )
        self.stock = self.supply("2")
        self.other_stock = self.supply("Newborn")

    def supply(self, size, **kwargs):
        return StockItem.objects.create(
            name="Diapers",
            category="diapers",
            size=size,
            unit="diapers",
            quantity=kwargs.pop("quantity", 20),
            **kwargs
        )

    def entry(self, child=None):
        return DiaperChange.objects.create(
            child=child or self.child, wet=True, solid=True, created_by=self.user
        )

    def quantity(self, item):
        item.refresh_from_db()
        return item.quantity

    def test_children_use_only_their_own_size_and_one_diaper_per_entry(self):
        entry = self.entry()
        self.assertEqual(self.quantity(self.stock), 19)
        self.assertEqual(self.quantity(self.other_stock), 20)
        self.entry(self.other)
        self.assertEqual(self.quantity(self.other_stock), 19)
        self.assertEqual(entry.stock_usage.status, "deducted")
        self.assertEqual(self.stock.movements.get().change, -1)
        self.assertEqual(self.stock.movements.get().balance, 19)

    def test_edit_is_idempotent_and_delete_returns_original_supply(self):
        entry = self.entry()
        replacement = self.supply("2")
        self.profile.diaper_stock = replacement
        self.profile.save()
        entry.notes = "Corrected note"
        entry.save()
        entry.save()
        self.assertEqual(self.quantity(self.stock), 19)
        self.assertEqual(self.quantity(replacement), 20)
        entry.delete()
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertEqual(self.quantity(replacement), 20)
        self.assertEqual(
            list(self.stock.movements.order_by("pk").values_list("balance", flat=True)),
            [19, 20],
        )

    def test_child_reassignment_transfers_stock(self):
        entry = self.entry()
        entry.child = self.other
        entry.save()
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertEqual(self.quantity(self.other_stock), 19)
        entry.save()
        entry.delete()
        self.assertEqual(self.quantity(self.other_stock), 20)

    def test_unsaved_child_change_is_not_transferred_with_update_fields(self):
        entry = self.entry()
        entry.child = self.other
        entry.notes = "Note only"
        entry.save(update_fields=["notes"])
        self.assertEqual(self.quantity(self.stock), 19)
        self.assertEqual(self.quantity(self.other_stock), 20)

    def test_ambiguous_supply_requires_selection(self):
        second = self.supply("2")
        entry = self.entry()
        self.assertEqual(entry.stock_usage.status, "ambiguous")
        self.assertEqual(self.quantity(self.stock), 20)
        self.profile.diaper_stock = second
        self.profile.save()
        self.entry()
        self.assertEqual(self.quantity(second), 19)
        entry.delete()
        self.assertEqual(self.quantity(second), 19)

    def test_next_size_and_outgrown_supplies_are_not_used(self):
        self.supply("3", stage="next")
        self.supply("1")
        self.supply("2", stage="outgrown")
        self.entry()
        self.assertEqual(self.quantity(self.stock), 19)

    def test_invalid_selected_supply_never_falls_back(self):
        for changes in [
            dict(archived=True),
            dict(stage="next"),
            dict(unit="packs"),
            dict(expiration_date=timezone.localdate() - timedelta(days=1)),
        ]:
            with self.subTest(changes=changes):
                item = self.supply("2")
                StockItem.objects.filter(pk=item.pk).update(**changes)
                self.profile.diaper_stock = item
                self.profile.save()
                entry = self.entry()
                self.assertEqual(entry.stock_usage.status, "invalid")
                self.assertEqual(self.quantity(item), 20)
                entry.delete()
        self.assertEqual(self.quantity(self.stock), 20)

    def test_shared_supply_is_automatically_used_for_both_children_with_same_size(self):
        self.other_profile.diaper_size = self.profile.diaper_size
        self.other_profile.save()
        first, second = self.entry(), self.entry(self.other)
        self.assertEqual(self.quantity(self.stock), 18)
        self.assertEqual(self.quantity(self.other_stock), 20)
        first.delete()
        self.assertEqual(self.quantity(self.stock), 19)
        second.delete()
        self.assertEqual(self.quantity(self.stock), 20)

    def test_age_range_fallback_for_children_without_size_preferences(self):
        ChildSupplyProfile.objects.all().delete()
        shared = self.supply("Household 0–3 months", min_age_months=0, max_age_months=3)
        self.entry()
        self.entry(self.other)
        self.assertEqual(self.quantity(shared), 18)
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertEqual(self.quantity(self.other_stock), 20)

    def test_age_boundary_and_overlapping_ranges(self):
        from datetime import date
        from .diapers import supply_matches

        self.child.birth_date = date(2026, 1, 22)
        self.profile.diaper_size = ""
        shared = self.supply("0–3 months", min_age_months=0, max_age_months=3)
        with patch(
            "inventory.diapers.timezone.localdate", return_value=date(2026, 5, 21)
        ):
            self.assertTrue(supply_matches(shared, self.child, self.profile))
        with patch(
            "inventory.diapers.timezone.localdate", return_value=date(2026, 5, 22)
        ):
            self.assertFalse(supply_matches(shared, self.child, self.profile))
        with patch(
            "inventory.diapers.timezone.localdate", return_value=date(2026, 1, 21)
        ):
            self.assertFalse(supply_matches(shared, self.child, self.profile))
        ChildSupplyProfile.objects.all().delete()
        second = self.supply("Another 0–3 months", max_age_months=3)
        self.assertEqual(self.entry().stock_usage.status, "ambiguous")
        self.assertEqual(self.quantity(shared), 20)
        self.assertEqual(self.quantity(second), 20)

    def test_selected_size_overrides_age_and_never_falls_back_to_smaller_size(self):
        self.stock.min_age_months = 10
        self.stock.save()
        age_stock = self.supply("0–3 months", max_age_months=3)
        self.entry()
        self.assertEqual(self.quantity(self.stock), 19)
        self.assertEqual(self.quantity(age_stock), 20)
        self.profile.diaper_size = "Much bigger"
        self.profile.save()
        self.assertEqual(self.entry().stock_usage.status, "missing")
        self.assertEqual(self.quantity(age_stock), 20)

    def test_designated_larger_supply_overrides_size_and_age(self):
        larger = self.supply("3", min_age_months=10)
        self.profile.diaper_stock = larger
        self.profile.save()
        self.entry()
        self.assertEqual(self.quantity(larger), 19)
        self.assertEqual(self.quantity(self.stock), 20)
        self.other_profile.diaper_stock = larger
        self.other_profile.save()
        self.entry(self.other)
        self.assertEqual(self.quantity(larger), 18)

    def test_no_size_or_age_range_does_not_guess(self):
        ChildSupplyProfile.objects.all().delete()
        self.assertEqual(self.entry().stock_usage.status, "missing")
        self.assertEqual(self.quantity(self.stock), 20)

    def test_empty_supply_saves_entry_without_negative_stock_or_later_charge(self):
        StockItem.objects.filter(pk=self.stock.pk).update(quantity=0)
        entry = self.entry()
        self.assertEqual(entry.stock_usage.status, "empty")
        StockItem.objects.filter(pk=self.stock.pk).update(quantity=20)
        entry.save()
        entry.delete()
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertFalse(StockMovement.objects.exists())

    def test_automatic_deduction_can_be_disabled(self):
        self.profile.auto_deduct_diapers = False
        self.profile.save()
        self.assertEqual(self.entry().stock_usage.status, "off")
        self.assertEqual(self.quantity(self.stock), 20)

    def test_legacy_edits_do_not_deduct(self):
        entry = DiaperChange(child=self.child, wet=True, solid=False)
        DiaperChange.objects.bulk_create([entry])
        entry.save()
        entry.delete()
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertFalse(StockMovement.objects.exists())

    def test_bulk_entry_deletion_returns_stock_but_child_deletion_does_not(self):
        self.entry()
        self.entry()
        DiaperChange.objects.all().delete()
        self.assertEqual(self.quantity(self.stock), 20)
        self.entry()
        Child.objects.filter(pk=self.child.pk).delete()
        self.assertEqual(self.quantity(self.stock), 19)

    def test_ledger_failure_rolls_back_entry_and_stock(self):
        with patch(
            "inventory.diapers.StockMovement.objects.using",
            side_effect=RuntimeError("ledger unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.entry()
        self.assertFalse(DiaperChange.objects.exists())
        self.assertFalse(DiaperStockUsage.objects.exists())
        self.assertEqual(self.quantity(self.stock), 20)

    def test_outer_transaction_rollback_restores_everything(self):
        with transaction.atomic():
            self.entry()
            transaction.set_rollback(True)
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertFalse(DiaperChange.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_settings_allow_any_household_supply_and_update_current_size(self):
        item = self.supply("3", min_age_months=10)
        form = SizeForm(
            {"diaper_size": "2", "auto_deduct_diapers": "on", "diaper_stock": item.pk},
            instance=self.profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.diaper_size, "3")
        self.entry()
        self.assertEqual(self.quantity(item), 19)
        item.expiration_date = timezone.localdate() - timedelta(days=1)
        item.save()
        form = SizeForm({"diaper_stock": item.pk}, instance=self.profile)
        self.assertFalse(form.is_valid())
        self.assertIn("diaper_stock", form.errors)

    def test_settings_page_exposes_selection(self):
        response = self.client.get(reverse("inventory:sizes", args=[self.child.pk]))
        self.assertContains(response, "Deduct diapers automatically")
        self.assertContains(response, "Automatic — matching size or age range")
        self.assertContains(response, "Sizes &amp; diaper supply")

    def test_web_entry_warns_when_stock_is_empty(self):
        from inventory.diapers import notify
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        StockItem.objects.filter(pk=self.stock.pk).update(quantity=0)
        entry = self.entry()
        request = RequestFactory().get("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        notify(request, entry)
        self.assertIn("out of stock", str(list(get_messages(request))[0]))

    def test_api_create_edit_and_delete_update_inventory(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            reverse("api:diaperchange-list"),
            {
                "child": self.child.pk,
                "time": timezone.now().isoformat(),
                "wet": True,
                "solid": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.quantity(self.stock), 19)
        url = reverse("api:diaperchange-detail", args=[response.data["id"]])
        response = client.patch(url, {"notes": "Updated"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.quantity(self.stock), 19)
        response = client.patch(url, {"child": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertEqual(self.quantity(self.other_stock), 19)
        self.assertEqual(client.delete(url).status_code, 204)
        self.assertEqual(self.quantity(self.other_stock), 20)

    def test_web_create_delete_and_empty_stock_warning(self):
        url = reverse("core:diaperchange-add")
        data = {
            "child": self.child.pk,
            "time": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "wet": "on",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        self.assertEqual(self.quantity(self.stock), 19)
        entry = DiaperChange.objects.get()
        other_user = get_user_model().objects.create_user(
            "other-parent", is_superuser=True
        )
        self.client.force_login(other_user)
        response = self.client.post(
            reverse("core:diaperchange-delete", args=[entry.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.quantity(self.stock), 20)
        self.assertEqual(self.stock.movements.first().user_id, other_user.pk)
        StockItem.objects.filter(pk=self.stock.pk).update(quantity=0)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DiaperChange.objects.exists())
        self.assertTrue(
            any("out of stock" in str(m) for m in get_messages(response.wsgi_request))
        )

    def test_manufacturer_weight_options_fit_existing_fields_and_forms(self):
        from .sizing import DIAPER_SIZES

        self.assertEqual(len(DIAPER_SIZES), 20)
        self.assertTrue(
            all(len(value) <= 40 and "lbs" in value for value in DIAPER_SIZES)
        )
        for route, args in (
            ("inventory:add", []),
            ("inventory:sizes", [self.child.pk]),
        ):
            response = self.client.get(reverse(route, args=args))
            self.assertContains(response, "12–18 lbs · Huggies 2")
            self.assertContains(response, "10–22 lbs · Pampers 2")
            self.assertContains(response, "Up to 10 lbs · Huggies Newborn")
            self.assertContains(response, "Diaper sizing references (US)")

    def test_shared_weight_range_supply_deducts_for_both_children(self):
        label = "12–18 lbs · Huggies 2"
        shared = self.supply(label)
        for profile in (self.profile, self.other_profile):
            form = SizeForm(
                {
                    "diaper_size": label,
                    "auto_deduct_diapers": True,
                    "diaper_stock": shared.pk,
                },
                instance=profile,
            )
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        first, second = self.entry(), self.entry(self.other)
        self.assertEqual(self.quantity(shared), 18)
        first.delete()
        self.assertEqual(self.quantity(shared), 19)
        self.assertEqual(self.quantity(self.stock), 20)

    def test_explicit_brands_are_not_matched_by_number_alone(self):
        shared = self.supply("12–18 lbs · Huggies 2")
        form = SizeForm(
            {"diaper_size": "10–22 lbs · Pampers 2", "diaper_stock": shared.pk},
            instance=self.profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["diaper_size"], shared.size)
        from .sizing import diaper_fit, same_diaper_size

        self.assertEqual(diaper_fit(shared.size, "10–22 lbs · Pampers 2"), "review")
        self.assertEqual(diaper_fit("16–28 lbs · Huggies 3", shared.size), "next")
        self.assertEqual(diaper_fit("8–14 lbs · Huggies 1", shared.size), "outgrown")
        self.assertFalse(same_diaper_size("10–22 lbs · Pampers 2", shared.size))
        self.assertTrue(same_diaper_size("Size 2", shared.size))
        self.assertTrue(same_diaper_size("NB", "Up to 10 lbs · Huggies Newborn"))
        self.assertTrue(same_diaper_size("Custom swim medium", "custom swim medium"))
