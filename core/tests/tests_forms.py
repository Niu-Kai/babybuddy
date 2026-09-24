# -*- coding: utf-8 -*-
import datetime
import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.test import Client as HttpClient
from django.utils import timezone
from django.utils.formats import get_format, reset_format_cache
from faker import Faker
from PIL import Image

from core import models


class FormsTestCaseBase(TestCase):
    c = None
    child = None
    user = None

    @classmethod
    def setUpClass(cls):
        super(FormsTestCaseBase, cls).setUpClass()
        fake = Faker()
        call_command("migrate", verbosity=0)

        cls.c = HttpClient()

        fake_user = fake.simple_profile()
        credentials = {"username": fake_user["username"], "password": fake.password()}
        cls.user = get_user_model().objects.create_user(
            is_superuser=True, **credentials
        )
        cls.c.login(**credentials)

        cls.child = models.Child.objects.create(
            first_name="Child", last_name="One", birth_date=timezone.localdate()
        )

    @staticmethod
    def localdate_string(datetime=None):
        """Converts an object to a local date string for form input."""
        reset_format_cache()
        date_format = get_format("DATE_INPUT_FORMATS")[0]
        return timezone.localdate(datetime).strftime(date_format)

    @staticmethod
    def localtime_string(datetime=None):
        """Converts an object to a local time string for form input."""
        reset_format_cache()
        datetime_format = get_format("DATETIME_INPUT_FORMATS")[0]
        return timezone.localtime(datetime).strftime(datetime_format)

    @staticmethod
    def image_upload(name="test.png", image_format="PNG"):
        file = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(file, format=image_format)
        return SimpleUploadedFile(name, file.getvalue(), content_type="image/png")

    @staticmethod
    def invalid_image_upload(name="test.txt"):
        return SimpleUploadedFile(name, b"not an image", content_type="text/plain")


class InitialValuesTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(InitialValuesTestCase, cls).setUpClass()
        cls.timer = models.Timer.objects.create(
            user=cls.user, start=timezone.localtime() - timezone.timedelta(minutes=30)
        )

    def test_child_with_one_child(self):
        page = self.c.get("/sleep/add/")
        self.assertEqual(page.context["form"].initial["child"], self.child)

    def test_child_with_parameter(self):
        child_two = models.Child.objects.create(
            first_name="Child", last_name="Two", birth_date=timezone.localdate()
        )

        page = self.c.get("/sleep/add/")
        self.assertTrue("child" not in page.context["form"].initial)

        page = self.c.get("/sleep/add/?child={}".format(self.child.slug))
        self.assertEqual(page.context["form"].initial["child"], self.child)

        page = self.c.get("/sleep/add/?child={}".format(child_two.slug))
        self.assertEqual(page.context["form"].initial["child"], child_two)

    def test_feeding_type(self):
        child_two = models.Child.objects.create(
            first_name="Child", last_name="Two", birth_date=timezone.localdate()
        )
        child_three = models.Child.objects.create(
            first_name="Child", last_name="Three", birth_date=timezone.localdate()
        )
        start_time = timezone.localtime() - timezone.timedelta(hours=4)
        end_time = timezone.localtime() - timezone.timedelta(hours=3, minutes=30)
        f_one = models.Feeding.objects.create(
            child=self.child,
            start=start_time,
            end=end_time,
            type="breast milk",
            method="left breast",
        )
        f_two = models.Feeding.objects.create(
            child=child_two,
            start=start_time,
            end=end_time,
            type="formula",
            method="bottle",
        )
        f_three = models.Feeding.objects.create(
            child=child_three,
            start=start_time,
            end=end_time,
            type="fortified breast milk",
            method="bottle",
        )

        page = self.c.get("/feedings/add/")
        self.assertTrue("type" not in page.context["form"].initial)

        page = self.c.get("/feedings/add/?child={}".format(self.child.slug))
        self.assertEqual(page.context["form"].initial["type"], f_one.type)
        self.assertFalse("method" in page.context["form"].initial)

        page = self.c.get("/feedings/add/?child={}".format(child_two.slug))
        self.assertEqual(page.context["form"].initial["type"], f_two.type)
        self.assertEqual(page.context["form"].initial["method"], f_two.method)

        page = self.c.get("/feedings/add/?child={}".format(child_three.slug))
        self.assertEqual(page.context["form"].initial["type"], f_three.type)
        self.assertEqual(page.context["form"].initial["method"], f_three.method)

    def test_start_end_set_from_timer(self):
        page = self.c.get("/sleep/add/?timer={}".format(self.timer.id))
        self.assertTrue("start" in page.context["form"].initial)
        self.assertTrue("end" in page.context["form"].initial)

    def test_start_end_not_set_from_invalid_timer(self):
        page = self.c.get("/sleep/add/?timer={}".format(42))
        self.assertTrue("start" not in page.context["form"].initial)
        self.assertTrue("end" not in page.context["form"].initial)

    def test_timer_name_set_from_timer(self):
        timer = models.Timer.objects.create(
            user=self.user,
            name="Timer Test",
            start=timezone.localtime() - timezone.timedelta(minutes=30),
        )

        page = self.c.get("/sleep/add/?timer={}".format(timer.id))
        self.assertEqual(page.context["form"].initial["timer"], "Timer Test")
        self.assertEqual(page.context["form"].fields["timer"].label, "Timer")
        self.assertContains(page, 'id="id_timer"')
        self.assertContains(page, 'value="Timer Test"')

    def test_timer_name_placed_after_child(self):
        timer = models.Timer.objects.create(
            user=self.user,
            name="Timer Test",
            start=timezone.localtime() - timezone.timedelta(minutes=30),
        )

        page = self.c.get("/sleep/add/?timer={}".format(timer.id))
        field_names = list(page.context["form"].fields)
        self.assertEqual(field_names.index("timer"), field_names.index("child") + 1)

    def test_timer_name_not_set_without_timer(self):
        page = self.c.get("/sleep/add/")
        self.assertNotIn("timer", page.context["form"].fields)

    def test_timer_name_not_set_from_invalid_timer(self):
        page = self.c.get("/sleep/add/?timer={}".format(42))
        self.assertNotIn("timer", page.context["form"].fields)

    def test_timer_name_not_set_from_non_numeric_timer(self):
        page = self.c.get("/sleep/add/?timer=not-a-number")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("timer", page.context["form"].fields)


class BMIFormsTestCase(FormsTestCaseBase):
    def test_manual_bmi_routes_are_read_only(self):
        entry = models.BMI.objects.create(
            child=self.child, bmi=30, date=timezone.localdate()
        )
        for path in ("/bmi/add/", f"/bmi/{entry.pk}/", f"/bmi/{entry.pk}/delete/"):
            self.assertEqual(
                self.c.post(path, {"child": self.child.pk, "bmi": 35}).status_code, 405
            )
            self.assertRedirects(self.c.get(path), "/bmi/")
        entry.refresh_from_db()
        self.assertEqual(entry.bmi, 30)


class ChildFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(ChildFormsTestCase, cls).setUpClass()
        cls.child = models.Child.objects.first()

    def test_add(self):
        params = {
            "first_name": "Child",
            "last_name": "Two",
            "birth_date": timezone.localdate(),
        }
        page = self.c.post("/children/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Child entry added")

    def test_add_with_picture(self):
        params = {
            "first_name": "Child",
            "last_name": "Two",
            "birth_date": timezone.localdate(),
            "picture": self.image_upload(),
        }
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            page = self.c.post("/children/add/", params, follow=True)
            self.assertEqual(page.status_code, 200)
            child = models.Child.objects.get(first_name="Child", last_name="Two")
            self.assertTrue(child.picture.name.startswith("child/picture/"))
            self.assertContains(page, "Child entry added")

    def test_add_rejects_invalid_picture(self):
        params = {
            "first_name": "Child",
            "last_name": "Two",
            "birth_date": timezone.localdate(),
            "picture": self.invalid_image_upload(),
        }
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            page = self.c.post("/children/add/", params)
            self.assertEqual(page.status_code, 200)
            self.assertIn(
                "Upload a valid image",
                page.context["form"].errors["picture"][0],
            )

    def test_edit(self):
        params = {
            "first_name": "Name",
            "last_name": "Changed",
            "birth_date": self.child.birth_date,
        }
        page = self.c.post(
            "/children/{}/edit/".format(self.child.slug), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.last_name, params["last_name"])
        self.assertContains(page, "Child entry updated")

    def test_delete(self):
        params = {"confirm_name": "Incorrect"}
        page = self.c.post(
            "/children/{}/delete/".format(self.child.slug), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.assertFormError(
            page.context["form"], "confirm_name", "Name does not match child name."
        )

        params["confirm_name"] = str(self.child)
        page = self.c.post(
            "/children/{}/delete/".format(self.child.slug), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Child entry deleted")


class DiaperChangeFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(DiaperChangeFormsTestCase, cls).setUpClass()
        cls.change = models.DiaperChange.objects.create(
            child=cls.child,
            time=timezone.localtime(),
            wet=True,
            solid=True,
            color="black",
            amount=0.45,
        )

    def test_add(self):
        child = models.Child.objects.first()
        params = {
            "child": child.id,
            "time": self.localtime_string(),
            "color": "black",
            "amount": 0.45,
        }
        page = self.c.post("/changes/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Diaper Change entry for {} added".format(str(child)))

    def test_edit(self):
        params = {
            "child": self.change.child.id,
            "time": self.localtime_string(),
            "wet": self.change.wet,
            "solid": self.change.solid,
            "color": self.change.color,
            "amount": 1.23,
        }
        page = self.c.post("/changes/{}/".format(self.change.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.change.refresh_from_db()
        self.assertEqual(self.change.amount, params["amount"])
        self.assertContains(
            page, "Diaper Change entry for {} updated".format(str(self.change.child))
        )

    def test_delete(self):
        page = self.c.post("/changes/{}/delete/".format(self.change.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Diaper Change entry deleted")


class FeedingFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(FeedingFormsTestCase, cls).setUpClass()
        cls.feeding = models.Feeding.objects.create(
            child=cls.child,
            start=timezone.localtime() - timezone.timedelta(hours=2),
            end=timezone.localtime() - timezone.timedelta(hours=1, minutes=30),
            type="breast milk",
            method="left breast",
            amount=2.5,
        )

    def test_add(self):
        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=30)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "type": "formula",
            "method": "bottle",
            "amount": 0,
        }
        page = self.c.post("/feedings/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Feeding entry for {} added".format(str(self.child)))

    def test_edit(self):
        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=30)
        params = {
            "child": self.feeding.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "type": self.feeding.type,
            "method": self.feeding.method,
            "amount": 100,
        }
        page = self.c.post("/feedings/{}/".format(self.feeding.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.feeding.refresh_from_db()
        self.assertEqual(self.feeding.amount, params["amount"])
        self.assertContains(
            page, "Feeding entry for {} updated".format(str(self.feeding.child))
        )

    def test_delete(self):
        page = self.c.post("/feedings/{}/delete/".format(self.feeding.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Feeding entry deleted")

    def test_bottle_feeding_no_overlap_with_past_entry(self):
        """Bottle feeding logged late should not overlap with later feedings."""
        # Create an existing feeding 30 minutes ago
        existing = models.Feeding.objects.create(
            child=self.child,
            start=timezone.localtime() - timezone.timedelta(minutes=30),
            end=timezone.localtime() - timezone.timedelta(minutes=15),
            type="breast milk",
            method="left breast",
        )
        # Add a bottle feeding from 60 minutes ago (before the existing one).
        # Without the fix, end would default to "now" and overlap.
        start = timezone.localtime() - timezone.timedelta(minutes=60)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "type": "formula",
            "amount": 4,
        }
        page = self.c.post("/feedings/bottle/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Feeding entry for {} added".format(str(self.child)))
        self.assertNotContains(page, "intersects the specified time period")


class HeadCircumferenceFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(HeadCircumferenceFormsTestCase, cls).setUpClass()
        cls.head_circumference = models.HeadCircumference.objects.create(
            child=cls.child,
            head_circumference=15,
            date=timezone.localdate() - timezone.timedelta(days=2),
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "head_circumference": 20,
            "date": self.localdate_string(),
        }

        page = self.c.post("/head-circumference/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Head Circumference entry for {} added".format(str(self.child))
        )

    def test_edit(self):
        params = {
            "child": self.head_circumference.child.id,
            "head_circumference": self.head_circumference.head_circumference + 1,
            "date": self.head_circumference.date,
        }
        page = self.c.post(
            "/head-circumference/{}/".format(self.head_circumference.id),
            params,
            follow=True,
        )
        self.assertEqual(page.status_code, 200)
        self.head_circumference.refresh_from_db()
        self.assertEqual(
            self.head_circumference.head_circumference, params["head_circumference"]
        )
        self.assertContains(
            page,
            "Head Circumference entry for {} updated".format(
                str(self.head_circumference.child)
            ),
        )

    def test_delete(self):
        page = self.c.post(
            "/head-circumference/{}/delete/".format(self.head_circumference.id),
            follow=True,
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Head Circumference entry deleted")


class HeightFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(HeightFormsTestCase, cls).setUpClass()
        cls.height = models.Height.objects.create(
            child=cls.child,
            height=12.5,
            date=timezone.localdate() - timezone.timedelta(days=2),
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "height": 13.5,
            "date": self.localdate_string(),
        }

        page = self.c.post("/height/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Height entry for {} added".format(str(self.child)))

    def test_edit(self):
        params = {
            "child": self.height.child.id,
            "height": self.height.height + 1,
            "date": self.height.date,
        }
        page = self.c.post("/height/{}/".format(self.height.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.height.refresh_from_db()
        self.assertEqual(self.height.height, params["height"])
        self.assertContains(
            page, "Height entry for {} updated".format(str(self.height.child))
        )

    def test_delete(self):
        page = self.c.post("/height/{}/delete/".format(self.height.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Height entry deleted")


class NoteFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(NoteFormsTestCase, cls).setUpClass()
        cls.note = models.Note.objects.create(
            child=cls.child,
            note="Test note!",
            time=timezone.localtime() - timezone.timedelta(days=2),
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "note": "New note",
            "time": self.localtime_string(),
        }

        page = self.c.post("/notes/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Note entry for {} added".format(str(self.child)))

    def test_add_with_image(self):
        params = {
            "child": self.child.id,
            "note": "New note",
            "image": self.image_upload(),
            "time": self.localtime_string(),
        }
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            page = self.c.post("/notes/add/", params, follow=True)
            self.assertEqual(page.status_code, 200)
            note = models.Note.objects.exclude(image="").latest("id")
            self.assertTrue(note.image.name.startswith("notes/images/"))
            self.assertContains(page, "Note entry for {} added".format(str(self.child)))

    def test_add_rejects_invalid_image(self):
        params = {
            "child": self.child.id,
            "note": "New note",
            "image": self.invalid_image_upload(),
            "time": self.localtime_string(),
        }
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            page = self.c.post("/notes/add/", params)
            self.assertEqual(page.status_code, 200)
            self.assertIn(
                "Upload a valid image", page.context["form"].errors["image"][0]
            )

    def test_edit(self):
        params = {
            "child": self.note.child.id,
            "note": "changed note",
            "time": self.note.time,
        }
        page = self.c.post("/notes/{}/".format(self.note.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual(self.note.note, params["note"])
        self.assertContains(
            page, "Note entry for {} updated".format(str(self.note.child))
        )

    def test_delete(self):
        page = self.c.post("/notes/{}/delete/".format(self.note.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Note entry deleted")


class PumpingFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(PumpingFormsTestCase, cls).setUpClass()
        start = timezone.localtime() - timezone.timedelta(days=1)
        end = start + timezone.timedelta(minutes=3)
        cls.bp = models.Pumping.objects.create(
            child=cls.child,
            amount=50.0,
            start=start,
            end=end,
        )

    def test_add(self):
        start = timezone.localtime() - timezone.timedelta(days=3)
        end = start + timezone.timedelta(minutes=5)
        params = {
            "child": self.child.id,
            "amount": "50.0",
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
        }

        page = self.c.post("/pumping/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pumping entry added")

    def test_edit(self):
        params = {
            "child": self.bp.child.id,
            "amount": self.bp.amount + 2,
            "start": self.localtime_string(self.bp.start),
            "end": self.localtime_string(self.bp.end + timezone.timedelta(minutes=15)),
        }
        page = self.c.post("/pumping/{}/".format(self.bp.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.bp.refresh_from_db()
        self.assertEqual(self.bp.amount, params["amount"])
        self.assertContains(page, "Pumping entry updated")

    def test_delete(self):
        page = self.c.post("/pumping/{}/delete/".format(self.bp.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pumping entry deleted")


class SleepFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(SleepFormsTestCase, cls).setUpClass()
        cls.sleep = models.Sleep.objects.create(
            child=cls.child,
            start=timezone.localtime() - timezone.timedelta(hours=6),
            end=timezone.localtime() - timezone.timedelta(hours=4),
        )

    def test_add(self):
        # Prevent potential sleep entry intersection errors.
        models.Sleep.objects.all().delete()

        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=2)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
        }

        page = self.c.post("/sleep/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sleep entry for {} added".format(str(self.child)))

    def test_edit(self):
        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=2)
        params = {
            "child": self.sleep.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
        }
        page = self.c.post("/sleep/{}/".format(self.sleep.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.sleep.refresh_from_db()
        self.assertEqual(self.localtime_string(self.sleep.end), params["end"])
        self.assertContains(
            page, "Sleep entry for {} updated".format(str(self.sleep.child))
        )

    def test_delete(self):
        page = self.c.post("/sleep/{}/delete/".format(self.sleep.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sleep entry deleted")

    def test_nap_default(self):
        models.Sleep.settings.nap_start_min = datetime.time(0, 0, 0)
        models.Sleep.settings.nap_start_max = datetime.time(23, 59, 59)
        response = self.c.get("/sleep/add/")
        self.assertTrue(response.context["form"].initial["nap"])

    def test_not_nap_default(self):
        models.Sleep.settings.nap_start_min = datetime.time(0, 0, 0)
        models.Sleep.settings.nap_start_max = datetime.time(0, 0, 0)
        response = self.c.get("/sleep/add/")
        self.assertFalse(response.context["form"].initial["nap"])


class TaggedFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(TaggedFormsTestCase, cls).setUpClass()

        cls.note = models.Note.objects.create(
            child=cls.child,
            note="Setup note",
            time=timezone.now() - timezone.timedelta(days=2),
        )
        cls.note.tags.add("oldtag")
        cls.oldtag = models.Tag.objects.filter(slug="oldtag").first()

    def test_add_no_tags(self):
        params = {
            "child": self.child.id,
            "note": "note with no tags",
            "time": (timezone.now() - timezone.timedelta(minutes=1)).isoformat(),
        }

        page = self.c.post("/notes/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "note with no tags")

    def test_add_with_tags(self):
        params = {
            "child": self.child.id,
            "note": "this note has tags",
            "time": (timezone.now() - timezone.timedelta(minutes=1)).isoformat(),
            "tags": 'A,B,"setup tag"',
        }

        old_notes = list(models.Note.objects.all())

        page = self.c.post("/notes/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "this note has tags")

        new_notes = list(models.Note.objects.all())

        # Find the new tag and extract its tags
        old_pks = [n.pk for n in old_notes]
        new_note = [n for n in new_notes if n.pk not in old_pks][0]
        new_note_tag_names = [t.name for t in new_note.tags.all()]

        self.assertSetEqual(set(new_note_tag_names), {"A", "B", "setup tag"})

    def test_edit(self):
        old_tag_last_used = self.oldtag.last_used

        params = {
            "child": self.note.child.id,
            "note": "Edited note",
            "time": self.localdate_string(),
            "tags": "oldtag,newtag",
        }
        page = self.c.post("/notes/{}/".format(self.note.id), params, follow=True)
        self.assertEqual(page.status_code, 200)

        self.note.refresh_from_db()
        self.oldtag.refresh_from_db()
        self.assertEqual(self.note.note, params["note"])
        self.assertContains(
            page, "Note entry for {} updated".format(str(self.note.child))
        )

        self.assertSetEqual(
            set(t.name for t in self.note.tags.all()), {"oldtag", "newtag"}
        )

        # Old tag remains old, because it was not added
        self.assertEqual(old_tag_last_used, self.oldtag.last_used)

        # Second phase: Remove all tags then add "oldtag" through posting
        # which should update the last_used tag
        self.note.tags.clear()
        self.note.save()

        params = {
            "child": self.note.child.id,
            "note": "Edited note (2)",
            "time": self.localdate_string(),
            "tags": "oldtag",
        }
        page = self.c.post("/notes/{}/".format(self.note.id), params, follow=True)
        self.assertEqual(page.status_code, 200)

        self.note.refresh_from_db()
        self.oldtag.refresh_from_db()

        self.assertLess(old_tag_last_used, self.oldtag.last_used)

    def test_delete(self):
        page = self.c.post("/notes/{}/delete/".format(self.note.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Note entry deleted")


class TemperatureFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(TemperatureFormsTestCase, cls).setUpClass()
        cls.temp = models.Temperature.objects.create(
            child=cls.child,
            temperature=98.6,
            time=timezone.localtime() - timezone.timedelta(days=1),
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "temperature": "98.6",
            "time": self.localtime_string(),
        }

        page = self.c.post("/temperature/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Temperature entry for {} added".format(str(self.child))
        )

    def test_edit(self):
        params = {
            "child": self.temp.child.id,
            "temperature": self.temp.temperature + 2,
            "time": self.localtime_string(),
        }
        page = self.c.post("/temperature/{}/".format(self.temp.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.temperature, params["temperature"])
        self.assertContains(
            page, "Temperature entry for {} updated".format(str(self.temp.child))
        )

    def test_delete(self):
        page = self.c.post("/temperature/{}/delete/".format(self.temp.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Temperature entry deleted")


class TummyTimeFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(TummyTimeFormsTestCase, cls).setUpClass()
        cls.tt = models.TummyTime.objects.create(
            child=cls.child,
            start=timezone.localtime() - timezone.timedelta(hours=2),
            end=timezone.localtime() - timezone.timedelta(hours=1, minutes=50),
        )

    def test_add(self):
        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=2)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "milestone": "",
        }

        page = self.c.post("/tummy-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Tummy Time entry for {} added".format(str(self.child))
        )

    def test_edit(self):
        end = timezone.localtime()
        start = end - timezone.timedelta(minutes=1, seconds=32)
        params = {
            "child": self.tt.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "milestone": "Moved head!",
            "notes": "Seemed to enjoy it.",
        }
        page = self.c.post("/tummy-time/{}/".format(self.tt.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.milestone, params["milestone"])
        self.assertEqual(self.tt.notes, params["notes"])
        self.assertContains(
            page, "Tummy Time entry for {} updated".format(str(self.tt.child))
        )

    def test_delete(self):
        page = self.c.post("/tummy-time/{}/delete/".format(self.tt.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Tummy Time entry deleted")


class TimerFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(TimerFormsTestCase, cls).setUpClass()
        cls.timer = models.Timer.objects.create(user=cls.user)

    def test_add(self):
        params = {
            "child": self.child.id,
            "name": "Test Timer",
            "start": self.localtime_string(),
        }
        page = self.c.post("/timers/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, params["name"])
        self.assertContains(page, params["child"])

    def test_edit(self):
        start_time = self.timer.start - timezone.timedelta(hours=1)
        params = {"name": "New Timer Name", "start": self.localtime_string(start_time)}
        page = self.c.post(
            "/timers/{}/edit/".format(self.timer.id), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, params["name"])
        self.timer.refresh_from_db()
        self.assertEqual(self.localtime_string(self.timer.start), params["start"])

    def test_edit_without_child_message(self):
        timer = models.Timer.objects.create(user=self.user)
        params = {
            "child": "",
            "name": "Childless Timer",
            "start": self.localtime_string(timer.start),
        }
        page = self.c.post("/timers/{}/edit/".format(timer.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Timer entry for None updated.")
        self.assertContains(page, "Timer entry updated.")


class ValidationsTestCase(FormsTestCaseBase):
    def test_validate_date(self):
        future = timezone.localtime() + timezone.timedelta(days=10)
        params = {
            "child": self.child,
            "weight": "8.5",
            "date": self.localdate_string(future),
        }
        entry = models.Weight.objects.create(**params)

        page = self.c.post("/weight/{}/".format(entry.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertFormError(
            page.context["form"], "date", "Date can not be in the future."
        )

    def test_validate_duration(self):
        end = timezone.localtime() - timezone.timedelta(minutes=10)
        start = end + timezone.timedelta(minutes=5)
        params = {
            "child": self.child,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "milestone": "",
        }

        page = self.c.post("/tummy-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertFormError(
            page.context["form"], None, "Start time must come before end time."
        )

        start = end - timezone.timedelta(weeks=53)
        params["start"] = self.localtime_string(start)
        page = self.c.post("/tummy-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertFormError(page.context["form"], None, "Duration too long.")

    def test_validate_time(self):
        future = timezone.localtime() + timezone.timedelta(hours=1)
        params = {
            "child": self.child,
            "start": self.localtime_string(),
            "end": self.localtime_string(future),
            "milestone": "",
        }

        page = self.c.post("/tummy-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertFormError(
            page.context["form"], "end", "Date/time can not be in the future."
        )

    def test_validate_unique_period(self):
        entry = models.TummyTime.objects.create(
            child=self.child,
            start=timezone.localtime() - timezone.timedelta(minutes=10),
            end=timezone.localtime() - timezone.timedelta(minutes=5),
        )

        start = entry.start - timezone.timedelta(minutes=2)
        end = entry.end + timezone.timedelta(minutes=2)
        params = {
            "child": entry.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(end),
            "milestone": "",
        }

        page = self.c.post("/tummy-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page,
            "Another entry intersects the specified time period.",
        )
        self.assertContains(
            page,
            "Conflicting entry:",
        )
        self.assertContains(
            page,
            "/tummy-time/{}/".format(entry.id),
        )


class WeightFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(WeightFormsTestCase, cls).setUpClass()
        cls.weight = models.Weight.objects.create(
            child=cls.child,
            weight=8,
            date=timezone.localdate() - timezone.timedelta(days=2),
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "weight": 8.5,
            "date": self.localdate_string(),
        }

        page = self.c.post("/weight/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Weight entry for {} added".format(str(self.child)))

    def test_edit(self):
        params = {
            "child": self.weight.child.id,
            "weight": self.weight.weight + 1,
            "date": self.localdate_string(),
        }
        page = self.c.post("/weight/{}/".format(self.weight.id), params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.weight.refresh_from_db()
        self.assertEqual(self.weight.weight, params["weight"])
        self.assertContains(
            page, "Weight entry for {} updated".format(str(self.weight.child))
        )

    def test_delete(self):
        page = self.c.post("/weight/{}/delete/".format(self.weight.id), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Weight entry deleted")


class MedicationFormsTestCase(FormsTestCaseBase):
    @classmethod
    def setUpClass(cls):
        super(MedicationFormsTestCase, cls).setUpClass()
        cls.medication = models.Medication.objects.create(
            child=cls.child,
            name="Tylenol",
            dosage=5.0,
            dosage_unit="ml",
            time=timezone.localtime() - timezone.timedelta(hours=2),
            next_dose_interval=timezone.timedelta(hours=4),
            notes="Test medication",
        )

    def test_add(self):
        params = {
            "child": self.child.id,
            "name": "Ibuprofen",
            "dosage": "2.5",
            "dosage_unit": "ml",
            "time": self.localtime_string(),
            "next_dose_interval": "4",
            "notes": "New medication entry",
        }

        page = self.c.post("/medication/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Medication entry for {} added".format(str(self.child))
        )

    def test_add_without_interval(self):
        params = {
            "child": self.child.id,
            "name": "Vitamin D",
            "dosage": "1",
            "dosage_unit": "drops",
            "time": self.localtime_string(),
            "notes": "Daily vitamin",
        }

        page = self.c.post("/medication/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Medication entry for {} added".format(str(self.child))
        )

    def test_add_with_tags(self):
        params = {
            "child": self.child.id,
            "name": "Acetaminophen",
            "dosage": "3.0",
            "dosage_unit": "ml",
            "time": self.localtime_string(),
            "next_dose_interval": "6",
            "tags": "fever,pain",
        }

        page = self.c.post("/medication/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Medication entry for {} added".format(str(self.child))
        )

    def test_edit(self):
        params = {
            "child": self.medication.child.id,
            "name": self.medication.name,
            "dosage": self.medication.dosage + 1.0,
            "dosage_unit": self.medication.dosage_unit,
            "time": self.localtime_string(self.medication.time),
            "next_dose_interval": "8",
            "notes": "Updated medication entry",
        }
        page = self.c.post(
            "/medication/{}/".format(self.medication.id), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.medication.refresh_from_db()
        self.assertEqual(self.medication.dosage, params["dosage"])
        self.assertEqual(self.medication.notes, params["notes"])
        self.assertContains(
            page, "Medication entry for {} updated".format(str(self.medication.child))
        )

    def test_edit_change_interval(self):
        params = {
            "child": self.medication.child.id,
            "name": self.medication.name,
            "dosage": self.medication.dosage,
            "dosage_unit": self.medication.dosage_unit,
            "time": self.localtime_string(self.medication.time),
            "next_dose_interval": "12",
            "notes": self.medication.notes,
        }
        page = self.c.post(
            "/medication/{}/".format(self.medication.id), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.medication.refresh_from_db()
        self.assertContains(
            page, "Medication entry for {} updated".format(str(self.medication.child))
        )

    def test_edit_remove_interval(self):
        params = {
            "child": self.medication.child.id,
            "name": self.medication.name,
            "dosage": self.medication.dosage,
            "dosage_unit": self.medication.dosage_unit,
            "time": self.localtime_string(self.medication.time),
            "notes": self.medication.notes,
        }
        page = self.c.post(
            "/medication/{}/".format(self.medication.id), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.medication.refresh_from_db()
        self.assertIsNone(self.medication.next_dose_interval)

    def test_delete(self):
        page = self.c.post(
            "/medication/{}/delete/".format(self.medication.id), follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Medication entry deleted")

    def test_form_without_dosage(self):
        # Dosage is now optional — form should be valid without it
        params = {
            "child": self.child.id,
            "name": "Vitamin D",
            "time": self.localtime_string(),
        }

        page = self.c.post("/medication/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Medication entry for {} added".format(str(self.child))
        )

    def test_form_validation_future_time(self):
        future_time = timezone.localtime() + timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "name": "Test Medication",
            "dosage": "5.0",
            "dosage_unit": "ml",
            "time": self.localtime_string(future_time),
        }

        page = self.c.post("/medication/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertFormError(
            page.context["form"], "time", "Date/time can not be in the future."
        )


class OverlapConfirmationTestCase(FormsTestCaseBase):
    """An overlapping entry can be saved after explicit confirmation (#702)."""

    def _params(self, allow=False):
        start = timezone.localtime() - timezone.timedelta(hours=2)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=30)),
            "nap": False,
        }
        if allow:
            params["allow_overlap"] = "on"
        return params

    def test_overlap_offers_confirmation_then_saves(self):
        start = timezone.localtime() - timezone.timedelta(hours=2)
        models.Sleep.objects.create(
            child=self.child,
            start=start + timezone.timedelta(minutes=10),
            end=start + timezone.timedelta(minutes=20),
        )

        page = self.c.post("/sleep/add/", self._params(), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "intersects the specified time period")
        self.assertContains(page, "Save anyway")
        self.assertEqual(models.Sleep.objects.filter(child=self.child).count(), 1)

        page = self.c.post("/sleep/add/", self._params(allow=True), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sleep entry for {} added".format(str(self.child)))
        self.assertEqual(models.Sleep.objects.filter(child=self.child).count(), 2)

    def test_no_conflict_no_checkbox(self):
        page = self.c.post("/sleep/add/", self._params(), follow=True)
        self.assertNotContains(page, "Save anyway")


class FeedingOptionalEndTestCase(FormsTestCaseBase):
    """A feeding can be recorded without an end time (#772)."""

    def test_feeding_without_end(self):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": "",
            "type": "breast milk",
            "method": "left breast",
        }
        page = self.c.post("/feedings/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Feeding entry for {} added".format(str(self.child)))
        feeding = models.Feeding.objects.filter(child=self.child).first()
        self.assertEqual(feeding.start, feeding.end)
        self.assertEqual(feeding.duration, timezone.timedelta(0))


class SingleChildFormTestCase(FormsTestCaseBase):
    """With one child the child field is hidden (#889)."""

    def test_child_hidden_for_single_child(self):
        self.assertEqual(models.Child.objects.count(), 1)
        page = self.c.get("/sleep/add/")
        self.assertContains(
            page,
            'type="hidden" name="child" value="{}" id="id_child"'.format(self.child.id),
        )
        self.assertNotContains(page, "btn-group-toggle")

    def test_child_selector_for_several_children(self):
        second = models.Child.objects.create(
            first_name="Child", last_name="Two", birth_date=timezone.localdate()
        )
        try:
            page = self.c.get("/sleep/add/")
            self.assertNotContains(
                page, 'name="child" value="{}" id="id_child"'.format(self.child.id)
            )
            self.assertContains(page, "btn-group-toggle")
        finally:
            second.delete()


class MedicationRepeatTestCase(FormsTestCaseBase):
    """`?repeat=<id>` pre-fills a new dose from an existing entry (#1068)."""

    def test_repeat_prefills(self):
        source = models.Medication.objects.create(
            child=self.child,
            name="Paracetamol",
            dosage=2.5,
            dosage_unit="ml",
            time=timezone.localtime() - timezone.timedelta(hours=6),
            next_dose_interval=timezone.timedelta(hours=4),
        )
        page = self.c.get("/medication/add/?repeat={}".format(source.id))
        self.assertEqual(page.status_code, 200)
        form = page.context["form"]
        self.assertEqual(form.initial["name"], "Paracetamol")
        self.assertEqual(form.initial["dosage"], 2.5)
        self.assertEqual(form.initial["dosage_unit"], "ml")
        self.assertEqual(form.initial["next_dose_interval"], 4.0)

    def test_repeat_ignores_garbage(self):
        page = self.c.get("/medication/add/?repeat=nope")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("name", page.context["form"].initial)


class PumpingSideTestCase(FormsTestCaseBase):
    """Pumping records which side was pumped (#949)."""

    def test_side_saved_and_listed(self):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=15)),
            "amount": 90,
            "side": "left",
        }
        page = self.c.post("/pumping/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pumping entry added")
        pumping = models.Pumping.objects.first()
        self.assertEqual(pumping.side, "left")
        page = self.c.get("/pumping/")
        self.assertContains(page, "Left")

    def test_side_optional(self):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=15)),
            "amount": 90,
        }
        page = self.c.post("/pumping/add/", params, follow=True)
        self.assertContains(page, "Pumping entry added")
        self.assertIsNone(models.Pumping.objects.first().side)


class SmallIssuesTestCase(FormsTestCaseBase):
    def test_bottle_feeding_has_no_solid_food(self):
        from core.forms import BottleFeedingForm

        choices = [choice[0] for choice in BottleFeedingForm().fields["type"].choices]
        self.assertNotIn("solid food", choices)
        self.assertIn("formula", choices)

    def test_default_diaper_amount(self):
        from dbsettings.loading import set_setting_value

        page = self.c.get("/changes/add/")
        self.assertIsNone(page.context["form"].initial.get("amount"))
        set_setting_value("core.models", "DiaperChange", "default_amount", 1.0)
        try:
            page = self.c.get("/changes/add/")
            self.assertEqual(page.context["form"].initial.get("amount"), 1.0)
        finally:
            set_setting_value("core.models", "DiaperChange", "default_amount", 0)

    def test_birth_time_supports_seconds_picker(self):
        page = self.c.get("/children/{}/edit/".format(self.child.slug))
        self.assertContains(page, 'name="birth_time"')
        self.assertContains(page, 'data-choice-kind="time"')
        self.assertIn("%S", page.context["form"].fields["birth_time"].widget.format)

    def test_child_slug_editable(self):
        params = {
            "first_name": self.child.first_name,
            "last_name": self.child.last_name,
            "birth_date": self.localdate_string(),
            "slug": "kiddo",
        }
        page = self.c.post(
            "/children/{}/edit/".format(self.child.slug), params, follow=True
        )
        self.assertEqual(page.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.slug, "kiddo")

        params["slug"] = ""
        page = self.c.post("/children/kiddo/edit/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.slug, "child-one")

    def test_child_slug_must_be_unique(self):
        other = models.Child.objects.create(
            first_name="Other", last_name="Kid", birth_date=timezone.localdate()
        )
        params = {
            "first_name": self.child.first_name,
            "last_name": self.child.last_name,
            "birth_date": self.localdate_string(),
            "slug": other.slug,
        }
        page = self.c.post("/children/{}/edit/".format(self.child.slug), params)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "already uses this slug")
        other.delete()


class CreatedByTestCase(FormsTestCaseBase):
    """Entries record who added them (#900)."""

    def test_form_records_user(self):
        params = {
            "child": self.child.id,
            "time": self.localtime_string(),
            "wet": True,
            "solid": False,
        }
        page = self.c.post("/changes/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        change = models.DiaperChange.objects.filter(child=self.child).first()
        self.assertEqual(change.created_by, self.user)
        page = self.c.get("/changes/")
        self.assertContains(page, self.user.get_username())

    def test_edit_keeps_creator(self):
        change = models.DiaperChange.objects.create(
            child=self.child, time=timezone.localtime(), wet=True, solid=False
        )
        self.assertIsNone(change.created_by)
        params = {
            "child": self.child.id,
            "time": self.localtime_string(),
            "wet": True,
            "solid": True,
        }
        self.c.post("/changes/{}/".format(change.id), params, follow=True)
        change.refresh_from_db()
        self.assertTrue(change.solid)
        self.assertIsNone(change.created_by)


class WeightTimeTestCase(FormsTestCaseBase):
    """Weight entries can carry the time of the weigh-in (#863)."""

    def test_weight_with_time(self):
        params = {
            "child": self.child.id,
            "weight": 4.2,
            "date": self.localdate_string(),
            "time": "07:30",
        }
        page = self.c.post("/weight/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Weight entry for {} added".format(str(self.child)))
        weight = models.Weight.objects.filter(child=self.child).first()
        self.assertEqual(weight.time.strftime("%H:%M"), "07:30")
        page = self.c.get("/weight/")
        self.assertContains(page, "7:30")

    def test_same_day_ordering(self):
        today = timezone.localdate()
        early = models.Weight.objects.create(
            child=self.child,
            weight=4.0,
            date=today,
            time=timezone.datetime(2000, 1, 1, 7).time(),
        )
        late = models.Weight.objects.create(
            child=self.child,
            weight=4.1,
            date=today,
            time=timezone.datetime(2000, 1, 1, 19).time(),
        )
        undated = models.Weight.objects.create(
            child=self.child, weight=4.05, date=today
        )
        ordered = list(models.Weight.objects.filter(child=self.child))
        self.assertEqual(ordered, [late, early, undated])


class AppointmentTestCase(FormsTestCaseBase):
    """Appointments: future entries, calendar, iCal feed, Google link (#408)."""

    def _add(self, title="Check-up", days=3):
        start = timezone.localtime() + timezone.timedelta(days=days)
        params = {
            "child": self.child.id,
            "title": title,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=30)),
            "location": "Clinic",
        }
        return self.c.post("/appointments/add/", params, follow=True)

    def test_add_and_list(self):
        page = self._add()
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Appointment entry for {} added".format(str(self.child))
        )
        appointment = models.Appointment.objects.get(title="Check-up")
        self.assertFalse(appointment.is_past)
        self.assertIn("calendar.google.com", appointment.google_calendar_url)
        self.assertIn("Check-up", appointment.google_calendar_url)
        page = self.c.get("/appointments/")
        self.assertContains(page, "Check-up")
        self.assertContains(page, "appointments.ics?token=")

    def test_end_before_start_rejected(self):
        start = timezone.localtime() + timezone.timedelta(days=1)
        params = {
            "child": self.child.id,
            "title": "Bad",
            "start": self.localtime_string(start),
            "end": self.localtime_string(start - timezone.timedelta(hours=1)),
        }
        page = self.c.post("/appointments/add/", params)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "End time must come after start time")

    def test_calendar_page(self):
        self._add(days=1)
        page = self.c.get("/appointments/calendar/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Check-up")
        page = self.c.get("/appointments/calendar/?month=2030-02")
        self.assertEqual(page.status_code, 200)
        page = self.c.get("/appointments/calendar/?month=oops")
        self.assertEqual(page.status_code, 200)

    def test_ical_feed(self):
        self._add()
        from core.calendar_tokens import feed_token

        token = feed_token(self.user, self.child)
        url = "/children/{}/appointments.ics".format(self.child.slug)
        page = HttpClient().get(url + "?token=" + token)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page["Content-Type"], "text/calendar; charset=utf-8")
        body = page.content.decode()
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("SUMMARY:Check-up", body)
        self.assertIn("LOCATION:Clinic", body)
        page = HttpClient().get(url + "?token=nope")
        self.assertEqual(page.status_code, 403)


class LastBreastTestCase(FormsTestCaseBase):
    """ "Ended on" for both-breast feedings and the next-side hint (#1012)."""

    def test_both_breasts_records_side(self):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=20)),
            "type": "breast milk",
            "method": "both breasts",
            "last_breast": "left",
        }
        page = self.c.post("/feedings/add/", params, follow=True)
        self.assertContains(page, "Feeding entry for {} added".format(str(self.child)))
        feeding = models.Feeding.objects.filter(child=self.child).first()
        self.assertEqual(feeding.last_breast, "left")
        self.assertEqual(feeding.next_breast, "right")
        page = self.c.get("/children/{}/dashboard/".format(self.child.slug))
        self.assertContains(page, "Start next on")

    def test_side_cleared_for_other_methods(self):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=20)),
            "type": "breast milk",
            "method": "left breast",
            "last_breast": "left",
        }
        self.c.post("/feedings/add/", params, follow=True)
        feeding = models.Feeding.objects.filter(child=self.child).first()
        self.assertIsNone(feeding.last_breast)
        self.assertEqual(feeding.next_breast, "right")


class MixedFeedingTestCase(FormsTestCaseBase):
    """One feeding with two types and amounts, with totals (#837, #508)."""

    def _params(self, **extra):
        start = timezone.localtime() - timezone.timedelta(hours=1)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=20)),
            "type": "breast milk",
            "method": "bottle",
            "amount": 60,
            "secondary_type": "formula",
            "secondary_amount": 40,
        }
        params.update(extra)
        return params

    def test_mixed_feeding_totals(self):
        page = self.c.post("/feedings/add/", self._params(), follow=True)
        self.assertContains(page, "Feeding entry for {} added".format(str(self.child)))
        feeding = models.Feeding.objects.filter(child=self.child).first()
        self.assertEqual(feeding.total_amount, 100)
        self.assertEqual(feeding.type_display, "Breast milk + Formula")
        self.assertEqual(feeding.amount_display, "60 + 40 = 100")
        page = self.c.get("/feedings/")
        self.assertContains(page, "Breast milk + Formula")
        self.assertContains(page, "60 + 40 = 100")
        from dashboard.templatetags import cards
        from django.contrib.auth import get_user_model

        class Request:
            user = get_user_model().objects.first()

        recent = cards.card_feeding_recent({"request": Request()}, self.child)
        # the feeding may fall on yesterday around midnight; sum the week
        self.assertEqual(sum(day["total"] for day in recent["feedings"]), 100)

    def test_second_amount_needs_type(self):
        page = self.c.post("/feedings/add/", self._params(secondary_type=""))
        self.assertContains(page, "Choose the type of the second amount")

    def test_second_type_must_differ(self):
        page = self.c.post("/feedings/add/", self._params(secondary_type="breast milk"))
        self.assertContains(page, "must differ from the first")


class NewActivityTypesTestCase(FormsTestCaseBase):
    """Bath time, reflux and food entries (#1112, #1031, #1032)."""

    def test_bath_time(self):
        start = timezone.localtime() - timezone.timedelta(hours=2)
        params = {
            "child": self.child.id,
            "start": self.localtime_string(start),
            "end": self.localtime_string(start + timezone.timedelta(minutes=15)),
        }
        page = self.c.post("/bath-time/add/", params, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page, "Bath Time entry for {} added".format(str(self.child))
        )
        bath = models.BathTime.objects.get(child=self.child)
        self.assertEqual(bath.duration, timezone.timedelta(minutes=15))
        self.assertContains(self.c.get("/bath-time/"), "15 minutes")
        page = self.c.get(
            "/children/{}/?date={}".format(
                self.child.slug, timezone.localtime(bath.end).date().isoformat()
            )
        )
        self.assertContains(page, self.child.first_name + " · Bath time")
        self.assertContains(page, 'class="timeline-event"', count=1)
        self.assertContains(page, "Duration: 15 minutes")
        event = page.context["timeline_objects"][0]
        self.assertEqual(event["time"], bath.start)
        self.assertEqual(event["session_end"], bath.end)

    def test_reflux(self):
        params = {
            "child": self.child.id,
            "time": self.localtime_string(),
            "severity": "moderate",
        }
        page = self.c.post("/reflux/add/", params, follow=True)
        self.assertContains(page, "Reflux entry for {} added".format(str(self.child)))
        self.assertContains(self.c.get("/reflux/"), "Moderate")

    def test_food(self):
        params = {
            "child": self.child.id,
            "time": self.localtime_string(),
            "name": "Banana",
            "amount": 30,
            "reaction": "liked",
        }
        page = self.c.post("/food/add/", params, follow=True)
        self.assertContains(page, "Food entry for {} added".format(str(self.child)))
        page = self.c.get("/food/")
        self.assertContains(page, "Banana")
        self.assertContains(page, "Liked it")
        self.user.settings.dashboard_hidden_cards = [
            key
            for key in self.user.settings.dashboard_hidden_cards
            if key != "food_recent"
        ]
        self.user.settings.save(update_fields=["dashboard_hidden_cards"])
        page = self.c.get("/children/{}/dashboard/".format(self.child.slug))
        self.assertContains(page, "Recent Foods")
        self.assertContains(page, "Banana")
