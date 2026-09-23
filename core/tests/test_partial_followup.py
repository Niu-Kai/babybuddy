from contextlib import closing
import datetime as dt
import json
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import uuid
import zipfile
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from core import forms, models
from core.photos import prepare_photo
from reports.growth import growth_chart, bmi_percentiles


class PartialFollowupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "partial-admin", is_superuser=True, is_staff=True
        )
        cls.user.settings.timezone = "America/New_York"
        cls.user.settings.save()
        cls.child = models.Child.objects.create(
            first_name="One",
            birth_date=dt.date(2020, 1, 1),
            due_date=dt.date(2020, 2, 12),
        )

    def setUp(self):
        timezone.activate("America/New_York")
        self.addCleanup(timezone.deactivate)
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def feeding(self, **extra):
        return {
            "child": self.child.pk,
            "appointment_date": "2023-11-05",
            "start_time": "01:30",
            "duration_minutes": "15",
            "type": "formula",
            "method": "tube",
            **extra,
        }

    def test_dst_choice_and_skipped_time(self):
        first = forms.FeedingForm(self.feeding(), user=self.user)
        self.assertFalse(first.is_valid())
        self.assertIn("time_occurrence", first.errors)
        values = []
        for fold in ("0", "1"):
            form = forms.FeedingForm(self.feeding(time_occurrence=fold), user=self.user)
            self.assertTrue(form.is_valid(), form.errors)
            values.append(form.cleaned_data["start"].astimezone(dt.timezone.utc))
        self.assertEqual(values[1] - values[0], dt.timedelta(hours=1))
        invalid = forms.FeedingForm(
            self.feeding(appointment_date="2024-03-10", start_time="02:30"),
            user=self.user,
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn("start_time", invalid.errors)

    def test_signed_current_reference_preserves_second_occurrence(self):
        instant = dt.datetime(2023, 11, 5, 6, 30, 42, tzinfo=dt.timezone.utc)
        with patch("django.utils.timezone.now", return_value=instant):
            original = forms.FeedingForm(user=self.user)
        bound = forms.FeedingForm(
            self.feeding(entry_reference=original.initial["entry_reference"]),
            user=self.user,
        )
        self.assertTrue(bound.is_valid(), bound.errors)
        self.assertEqual(
            bound.cleaned_data["start"].utcoffset(), dt.timedelta(hours=-5)
        )
        tampered = forms.FeedingForm(
            self.feeding(entry_reference="not-signed"), user=self.user
        )
        self.assertFalse(tampered.is_valid())

    def test_appointment_fold_choice_and_existing_fold(self):
        data = {
            "child": self.child.pk,
            "title": "Visit",
            "appointment_date": "2023-11-05",
            "start_time": "01:30",
            "duration_minutes": "30",
        }
        form = forms.AppointmentForm(data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("time_occurrence", form.errors)
        form = forms.AppointmentForm({**data, "time_occurrence": "1"}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        edit = forms.AppointmentForm(data, instance=instance, user=self.user)
        # Browser normally submits the signed hidden reference.
        edit.data = {**data, "entry_reference": edit.initial["entry_reference"]}
        self.assertTrue(edit.is_valid(), edit.errors)
        self.assertEqual(edit.cleaned_data["start"].utcoffset(), dt.timedelta(hours=-5))

    def test_tube_feeding_and_gestational_age(self):
        form = forms.FeedingForm(self.feeding(time_occurrence="0"), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().method, "tube")
        self.assertEqual(self.child.gestational_age_at_birth, "34 weeks, 0 days")
        response = self.client.get(reverse("dashboard:dashboard"), follow=True)
        self.assertContains(response, "Gestational age at birth")

    def test_potty_preset_is_idempotent_and_does_not_create_diapers(self):
        for _ in range(2):
            self.assertEqual(
                self.client.post(reverse("core:potty-preset")).status_code, 302
            )
        definition = models.ActivityType.objects.get(name="Potty attempt")
        self.assertIn("Both", definition.options())
        before = models.DiaperChange.objects.count()
        models.CustomActivity.objects.create(
            child=self.child, activity_type=definition, choice="Pee", checked=True
        )
        self.assertEqual(models.DiaperChange.objects.count(), before)
        self.assertEqual(self.client.get(reverse("core:potty-preset")).status_code, 405)

    def test_custom_offline_replay_and_revoked_definition(self):
        definition = models.ActivityType.objects.create(
            name="Exercise",
            track_duration=True,
            choice_label="Kind",
            choice_options="A\nB",
        )
        context = self.api.get("/api/offline-context").data
        item = next(
            x
            for x in context["activities"]
            if x["key"] == f"customactivity:{definition.pk}"
        )
        self.assertTrue(item["timer"])
        start = timezone.now() - dt.timedelta(hours=2)
        payload = {
            "user": self.user.pk,
            "key": str(uuid.uuid4()),
            "activity": item["key"],
            "entry": {
                "activity_type": definition.pk,
                "child": self.child.pk,
                "start": start.isoformat(),
                "end": (start + dt.timedelta(minutes=10)).isoformat(),
                "choice": "A",
            },
        }
        first = self.api.post("/api/offline-sync", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 200
        )
        self.assertEqual(models.CustomActivity.objects.count(), 1)
        definition.archived = True
        definition.save()
        payload["key"] = str(uuid.uuid4())
        self.assertEqual(
            self.api.post("/api/offline-sync", payload, format="json").status_code, 400
        )
        self.assertEqual(models.CustomActivity.objects.count(), 1)

    def test_batch_snapshot_retry_and_owner(self):
        notes = [
            models.Note.objects.create(
                child=self.child, note=str(i), time=timezone.now()
            )
            for i in range(105)
        ]
        job = models.DeletionBatch.objects.create(
            user=self.user, model_name="note", object_ids=[x.pk for x in notes]
        )
        url = reverse("core:batch-delete", args=[job.pk])
        self.assertEqual(self.client.post(url, {"position": 0}).status_code, 400)
        first = self.client.post(url, {"position": 0, "confirm": "yes"})
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["deleted"], 100)
        repeat = self.client.post(url, {"position": 0, "confirm": "yes"})
        self.assertEqual(repeat.json()["deleted"], 100)
        another = get_user_model().objects.create_user(
            "other-admin", is_staff=True, is_superuser=True
        )
        self.client.force_login(another)
        self.assertEqual(
            self.client.post(url, {"position": 100, "confirm": "yes"}).status_code, 404
        )
        self.client.force_login(self.user)
        last = self.client.post(url, {"position": 100, "confirm": "yes"})
        self.assertTrue(last.json()["done"])
        self.assertEqual(last.json()["deleted"], 105)

    def test_batch_rechecks_permission_and_csrf_before_each_batch(self):
        from django.contrib.auth.models import Permission
        from django.test import Client

        staff = get_user_model().objects.create_user("deletion-staff", is_staff=True)
        permission = Permission.objects.get(
            codename="delete_note", content_type__app_label="core"
        )
        staff.user_permissions.add(permission)
        notes = [
            models.Note.objects.create(
                child=self.child, note=str(i), time=timezone.now()
            )
            for i in range(101)
        ]
        job = models.DeletionBatch.objects.create(
            user=staff, model_name="note", object_ids=[n.pk for n in notes]
        )
        url = reverse("core:batch-delete", args=[job.pk])
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(staff)
        self.assertEqual(
            protected.post(url, {"position": 0, "confirm": "yes"}).status_code, 403
        )
        self.client.force_login(staff)
        self.assertEqual(
            self.client.post(url, {"position": 0, "confirm": "yes"}).json()["deleted"],
            100,
        )
        staff.user_permissions.remove(permission)
        self.assertEqual(
            self.client.post(url, {"position": 100, "confirm": "yes"}).status_code, 403
        )
        self.assertTrue(models.Note.objects.filter(pk=notes[-1].pk).exists())

    def test_growth_percentiles_are_optional_and_unit_converted(self):
        day = dt.timedelta(days=0)
        for sex in ("boy", "girl"):
            models.WeightPercentile.objects.filter(sex=sex, age_in_days=day).update(
                p3_weight=2, p15_weight=2.5, p50_weight=3, p85_weight=3.5, p97_weight=4
            )
        measurement = models.Weight.objects.create(
            child=self.child,
            date=self.child.corrected_birth_date,
            weight=3,
            entry_unit="kg",
        )
        with patch("reports.growth.plotly.plot", return_value="<div></div>") as render:
            growth_chart(
                models.Weight.objects.filter(pk=measurement.pk),
                self.child,
                "weight",
                "lb",
                ["boy"],
                percentiles=True,
            )
            data = render.call_args.args[0].data
            self.assertEqual(len(data), 11)
            p3 = next(
                t
                for t in data
                if t.meta
                and t.meta.get("reference") == "boy"
                and t.meta.get("percentile") == 3
            )
            self.assertAlmostEqual(p3.y[0], 4.41, places=2)
            self.assertTrue(p3.visible)
            self.assertFalse(
                next(
                    t for t in data if t.meta and t.meta.get("reference") == "girl"
                ).visible
            )
            growth_chart(
                models.Weight.objects.filter(pk=measurement.pk),
                self.child,
                "weight",
                "kg",
                ["boy"],
            )
            self.assertEqual(len(render.call_args.args[0].data), 3)
        self.assertEqual(
            bmi_percentiles()["boy"][0], [0, 11.254, 12.16, 13.407, 14.826, 16.13]
        )


class PhotoAndBackupTests(SimpleTestCase):
    def test_photo_orientation_resize_and_metadata(self):
        output = BytesIO()
        source = Image.new("RGB", (2000, 1000), "red")
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "Private note"
        source.save(output, format="JPEG", exif=exif)
        normalized = prepare_photo(
            SimpleUploadedFile(
                "private.jpg", output.getvalue(), content_type="image/jpeg"
            )
        )
        with Image.open(normalized) as image:
            self.assertEqual(image.size, (800, 1600))
            self.assertFalse(image.getexif())
        with self.assertRaises(ValidationError):
            prepare_photo(SimpleUploadedFile("bad.jpg", b"not an image"))

    def test_backup_is_readable_and_restorable(self):
        from scripts import update_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "live.sqlite3"
            with closing(sqlite3.connect(database)) as db:
                db.execute("CREATE TABLE entries (value TEXT)")
                db.execute("INSERT INTO entries VALUES ('example')")
                db.commit()
            media = root / "media"
            media.mkdir()
            (media / "photo.txt").write_text("photo")
            (root / "app.py").write_text("print('app')")
            with patch.object(update_app, "ROOT", root):
                folder = update_app.backup(root / "backup", database, media, ["app.py"])
            with closing(sqlite3.connect(folder / "db.sqlite3")) as restored:
                self.assertEqual(
                    restored.execute("SELECT value FROM entries").fetchone()[0],
                    "example",
                )
            with zipfile.ZipFile(folder / "files.zip") as files:
                self.assertEqual(files.read("media/photo.txt"), b"photo")
                self.assertIn("source/app.py", files.namelist())
