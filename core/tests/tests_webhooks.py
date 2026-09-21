# -*- coding: utf-8 -*-
from unittest import mock

from dbsettings.loading import set_setting_value
from django.test import TestCase
from django.utils import timezone

from core import models, webhooks


class WebhooksTestCase(TestCase):
    def setUp(self):
        set_setting_value("core.models", "Child", "url", "http://receiver.test/hook")
        set_setting_value("core.models", "Child", "secret", "s3cret")
        self.child = models.Child.objects.create(
            first_name="Hook", last_name="Kid", birth_date=timezone.localdate()
        )

    def tearDown(self):
        set_setting_value("core.models", "Child", "url", "")
        set_setting_value("core.models", "Child", "secret", "")

    def test_create_update_delete_events(self):
        with mock.patch("core.webhooks.deliver_async") as deliver:
            note = models.Note.objects.create(
                child=self.child, note="hello", time=timezone.now()
            )
            note.note = "changed"
            note.save()
            note_id = note.id
            note.delete()
        events = [call.args[1]["event"] for call in deliver.call_args_list[-3:]]
        self.assertEqual(events, ["note.created", "note.updated", "note.deleted"])
        url, payload, secret = deliver.call_args_list[-3].args
        self.assertEqual(url, "http://receiver.test/hook")
        self.assertEqual(secret, "s3cret")
        self.assertEqual(payload["child"]["slug"], self.child.slug)
        self.assertEqual(payload["data"]["note"], "hello")
        self.assertEqual(deliver.call_args_list[-1].args[1]["data"], {"id": note_id})

    def test_disabled_without_url(self):
        set_setting_value("core.models", "Child", "url", "")
        with mock.patch("core.webhooks.deliver_async") as deliver:
            models.Note.objects.create(
                child=self.child, note="quiet", time=timezone.now()
            )
        deliver.assert_not_called()

    def test_send_signs_and_survives_failure(self):
        payload = {"event": "note.created"}
        with mock.patch("core.webhooks.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = None
            webhooks.send("http://receiver.test/hook", payload, "s3cret")
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertTrue(request.get_header("X-babybuddy-signature"))
        with mock.patch(
            "core.webhooks.urllib.request.urlopen", side_effect=OSError("down")
        ):
            webhooks.send("http://receiver.test/hook", payload)  # must not raise
