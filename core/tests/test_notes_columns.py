from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import models


class RecordRows(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.rows = []
        self.current = None
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.current = []
            self.rows.append(self.current)
        elif tag in ("th", "td") and self.current is not None:
            self.current.append((attrs.get("data-column"), attrs.get("colspan")))


class NotesColumnTests(TestCase):
    def test_notes_are_a_real_column_and_topup_spans_visible_table(self):
        user = get_user_model().objects.create_superuser("column-parent", "", "test")
        self.client.force_login(user)
        child = models.Child.objects.create(
            first_name="Column", birth_date=timezone.localdate()
        )
        now = timezone.now() - timezone.timedelta(hours=1)
        note = "A useful note\n<script>unsafe</script>"
        models.Feeding.objects.create(
            child=child,
            start=now,
            end=now + timezone.timedelta(minutes=10),
            type="breast milk",
            method="left breast",
            notes=note,
            top_up_at=now + timezone.timedelta(minutes=15),
            top_up_type="formula",
            top_up_amount=20,
        )
        models.Weight.objects.create(
            child=child, date=timezone.localdate(), weight=3.5, notes=note
        )
        models.Appointment.objects.create(
            child=child,
            title="Checkup",
            start=timezone.now() + timezone.timedelta(days=1),
            notes=note,
        )
        for url_name in ("feeding-list", "weight-list", "appointment-list"):
            for scope in ("all", child.slug):
                with self.subTest(url=url_name, scope=scope):
                    page = self.client.get(
                        reverse("core:" + url_name), {"scope": scope}
                    )
                    self.assertEqual(page.status_code, 200)
                    body = page.content.decode()
                    self.assertIn('<th data-column="notes">', body)
                    self.assertIn('<td data-column="notes"', body)
                    self.assertNotIn('tr class="row-details" data-column="notes"', body)
                    self.assertNotIn("<script>unsafe</script>", body)
                    rows = RecordRows(body).rows
                    header = next(
                        row for row in rows if any(key == "notes" for key, span in row)
                    )
                    for row in rows:
                        if any(key == "notes" for key, span in row):
                            self.assertEqual(len(row), len(header))
                        for key, span in row:
                            if span and url_name == "feeding-list":
                                self.assertEqual(int(span), len(header))
