import csv
import io
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from babybuddy.models import ImportBatch
from core import models
from core.forms import ChildForm
from babybuddy.imports import REGISTRY, columns, process_rows


class ImportUITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "importer", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.user)
        self.child = models.Child.objects.create(
            first_name="Import Baby", birth_date=date(2020, 1, 1)
        )
        self.url = reverse("babybuddy:import")

    def upload(self, text, kind="note", **options):
        return self.client.post(
            self.url,
            {
                "kind": kind,
                "child": self.child.pk,
                "file": SimpleUploadedFile(
                    "entries.csv", text.encode("utf-8"), content_type="text/csv"
                ),
                **options,
            },
        )

    def test_preview_commit_and_repeat_confirmation(self):
        response = self.upload("time,note\n2021-01-01 12:00:00,Imported note\n")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm import")
        self.assertEqual(models.Note.objects.count(), 0)
        batch = response.context["batch"]
        self.assertEqual(
            self.client.post(self.url, {"confirm": batch.pk}).status_code, 302
        )
        self.assertEqual(models.Note.objects.get().note, "Imported note")
        self.assertEqual(models.Note.objects.get().created_by, self.user)
        self.client.post(self.url, {"confirm": batch.pk})
        self.assertEqual(models.Note.objects.count(), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.rows, [])
        self.assertIsNotNone(batch.completed_at)

    def test_row_errors_are_atomic(self):
        response = self.upload("time,note\n2021-01-01 12:00:00,Valid\nwrong,Invalid\n")
        self.assertEqual(response.context["row_errors"][0]["row"], 3)
        self.assertEqual(models.Note.objects.count(), 0)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_confirmation_conflict_rolls_back_and_shows_errors(self):
        response = self.upload(
            "first_name,last_name,birth_date\nConcurrent,Baby,2020-01-01\n",
            kind="child",
        )
        batch = response.context["batch"]
        models.Child.objects.create(
            first_name="Concurrent", last_name="Baby", birth_date=date(2020, 1, 1)
        )
        response = self.client.post(self.url, {"confirm": batch.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["row_errors"])
        batch.refresh_from_db()
        self.assertIsNone(batch.completed_at)
        self.assertTrue(batch.rows)

    def test_repeat_upload_uses_completed_receipt(self):
        csv_text = "time,note\n2021-01-01 12:00:00,Same file\n"
        response = self.upload(csv_text)
        self.client.post(self.url, {"confirm": response.context["batch"].pk})
        response = self.upload(csv_text)
        self.assertContains(response, "This file has already been imported.")
        self.assertEqual(models.Note.objects.count(), 1)

    def test_units_and_selected_child_override_export_metadata(self):
        response = self.upload(
            "id,child_id,date,weight,entry_unit\n999,999,2021-01-01,10,kg\n",
            kind="weight",
            unit="lb",
        )
        self.assertContains(response, "Confirm import")
        self.client.post(self.url, {"confirm": response.context["batch"].pk})
        record = models.Weight.objects.get()
        self.assertAlmostEqual(record.weight, 4.5359237, places=5)
        self.assertEqual(record.child, self.child)
        self.assertNotEqual(record.pk, 999)

    def test_wrong_columns_and_duplicate_rows(self):
        for text in (
            "note,note\na,b\n",
            "password,note\nsecret,a\n",
            "time,note\n2021-01-01 12:00:00,Same\n2021-01-01 12:00:00,Same\n",
        ):
            response = self.upload(text)
            self.assertIn("file", response.context["form"].errors)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_expired_foreign_and_invalid_receipts(self):
        response = self.upload("time,note\n2021-01-01 12:00:00,Private\n")
        batch = response.context["batch"]
        other = get_user_model().objects.create_user(
            "other-importer", is_staff=True, is_superuser=True
        )
        self.client.force_login(other)
        self.assertEqual(
            self.client.post(self.url, {"confirm": batch.pk}).status_code, 404
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(self.url, {"confirm": "invalid"}).status_code, 404
        )
        ImportBatch.objects.filter(pk=batch.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        self.assertEqual(
            self.client.post(self.url, {"confirm": batch.pk}).status_code, 302
        )
        self.assertEqual(models.Note.objects.count(), 0)

    def test_permission_and_child_scope_rechecked_at_confirmation(self):
        user = get_user_model().objects.create_user("limited-importer", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="add_note"))
        self.client.force_login(user)
        response = self.upload("time,note\n2021-01-01 12:00:00,Scoped\n")
        self.assertContains(response, "Confirm import")
        batch = response.context["batch"]
        user.settings.restrict_children = True
        user.settings.save()
        self.assertEqual(
            self.client.post(self.url, {"confirm": batch.pk}).status_code, 404
        )
        self.assertEqual(models.Note.objects.count(), 0)
        user.user_permissions.clear()
        self.assertEqual(
            self.client.post(self.url, {"confirm": batch.pk}).status_code, 403
        )

    def test_nonstaff_cannot_import(self):
        user = get_user_model().objects.create_user("caregiver")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_all_templates_and_choice_help(self):
        for kind in REGISTRY:
            page = self.client.get(self.url, {"kind": kind})
            self.assertEqual(page.status_code, 200, kind)
            template = self.client.get(self.url, {"kind": kind, "template": "1"})
            self.assertEqual(template.status_code, 200)
            self.assertNotIn(
                "id", next(csv.reader(io.StringIO(template.content.decode())))
            )
        self.assertContains(self.client.get(self.url, {"kind": "feeding"}), "formula")
        self.assertContains(self.client.get(self.url, {"kind": "feeding"}), "bottle")

    def test_historical_diapers_do_not_charge_stock(self):
        from inventory.models import StockItem, DiaperStockUsage

        stock = StockItem.objects.create(
            name="Shared diapers", category="diapers", unit="diapers", quantity=30
        )
        response = self.upload(
            "time,wet,solid\n2021-01-01 12:00:00,true,false\n", kind="diaperchange"
        )
        self.assertContains(response, "Confirm import")
        self.client.post(self.url, {"confirm": response.context["batch"].pk})
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 30)
        self.assertEqual(DiaperStockUsage.objects.count(), 0)
        record = models.DiaperChange.objects.get()
        self.assertTrue(record.wet)
        self.assertFalse(record.solid)
        record.notes = "Edited"
        record.save()
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 30)

    def test_tag_names_and_hidden_preferences_are_honored_as_file_data(self):
        self.user.settings.hidden_entry_fields = ["notes", "tags"]
        self.user.settings.save()
        response = self.upload(
            'date,weight,notes,tags\n2021-01-01,4,Keep note,"home,checkup"\n',
            kind="weight",
            unit="kg",
        )
        self.assertContains(response, "Confirm import")
        self.client.post(self.url, {"confirm": response.context["batch"].pk})
        record = models.Weight.objects.get()
        self.assertEqual(record.notes, "Keep note")
        self.assertEqual(set(record.tags.names()), {"home", "checkup"})


class BirthTimeSecondsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("birth-time")

    def test_both_formats_and_explicit_zero_seconds(self):
        for use_24, value in ((False, "1:05:37 PM"), (True, "13:05:37")):
            self.user.settings.use_24_hour_time = use_24
            form = ChildForm(
                user=self.user,
                data={
                    "first_name": f"Seconds {use_24}",
                    "birth_date": "2020-01-01",
                    "birth_time": value,
                },
            )
            self.assertTrue(form.is_valid(), form.errors)
            child = form.save()
            self.assertEqual(child.birth_time, time(13, 5, 37))
            rendered = ChildForm(user=self.user, instance=child)[
                "birth_time"
            ].as_widget()
            (
                self.assertIn(value, rendered)
                if use_24
                else self.assertIn("01:05:37 PM", rendered)
            )
            form = ChildForm(
                user=self.user,
                instance=child,
                data={
                    "first_name": child.first_name,
                    "birth_date": "2020-01-01",
                    "birth_time": "13:05:00",
                    "slug": child.slug,
                },
            )
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save().birth_time, time(13, 5))

    def test_other_time_widgets_stay_minute_only(self):
        from core.entry_timing import time_widget

        self.assertNotIn("%S", time_widget(self.user).format)
        self.assertIn("%S", time_widget(self.user, seconds=True).format)
