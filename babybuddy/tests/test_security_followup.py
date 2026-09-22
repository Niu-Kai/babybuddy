from datetime import timedelta
from unittest.mock import patch, Mock
from urllib.request import Request as URLRequest
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import TestCase, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from dbsettings.loading import set_setting_value

from api.pagination import BoundedLimitOffsetPagination
from api.views import DiaperChangeViewSet
from babybuddy.middleware import UserTimezoneMiddleware
from core import models, webhooks


class SecurityFollowupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("audit", is_superuser=True)
        self.child = models.Child.objects.create(
            first_name="Test", birth_date=timezone.localdate()
        )

    def test_api_related_queries_do_not_grow_with_entry_count(self):
        models.DiaperChange.objects.bulk_create(
            [
                models.DiaperChange(
                    child=self.child,
                    created_by=self.user,
                    time=timezone.now(),
                    wet=True,
                    solid=False,
                )
                for _ in range(20)
            ]
        )
        request = APIRequestFactory().get("/api/changes/", {"limit": 20})
        force_authenticate(request, self.user)
        with CaptureQueriesContext(connection) as queries:
            response = DiaperChangeViewSet.as_view({"get": "list"})(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertTrue(
            all(row["created_by"] == "audit" for row in response.data["results"])
        )
        self.assertLessEqual(len(queries), 4)

    def test_api_limits_are_capped_without_changing_default_pagination(self):
        paginator = BoundedLimitOffsetPagination()
        request = Request(APIRequestFactory().get("/api/changes/", {"limit": 99999999}))
        page = paginator.paginate_queryset(list(range(2001)), request)
        self.assertEqual(len(page), 1000)
        self.assertIn("offset=1000", paginator.get_next_link())
        request = Request(APIRequestFactory().get("/api/changes/"))
        self.assertEqual(
            len(paginator.paginate_queryset(list(range(2001)), request)), 100
        )

    def test_html_fragments_escape_dynamic_values(self):
        payload = '<img src=x onerror="alert(1)">'
        html = render_to_string("error/404.html", {"request_path": payload})
        self.assertNotIn(payload, html)
        self.assertIn("&lt;img", html)
        start = timezone.now() - timedelta(hours=2)
        models.Sleep.objects.create(
            child=self.child, start=start, end=start + timedelta(hours=1)
        )
        overlap = models.Sleep(
            child=self.child, start=start, end=start + timedelta(minutes=20)
        )
        with patch.object(models.Sleep, "__str__", return_value=payload):
            with self.assertRaises(ValidationError) as caught:
                overlap.clean()
        message = caught.exception.messages[0]
        self.assertNotIn(payload, message)
        self.assertIn("&lt;img", message)
        self.assertIn('<a href="', message)

    def test_timezone_does_not_leak_between_requests_or_after_failure(self):
        self.user.settings.timezone = "Asia/Tokyo"
        self.user.settings.save()
        request = RequestFactory().get("/")
        request.user = self.user
        observed = []

        def respond(request):
            observed.append(timezone.get_current_timezone_name())
            return HttpResponse()

        with timezone.override("UTC"):
            UserTimezoneMiddleware(respond)(request)
            self.assertEqual(observed, ["Asia/Tokyo"])
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")

            def fail(request):
                raise RuntimeError("test")

            with self.assertRaises(RuntimeError):
                UserTimezoneMiddleware(fail)(request)
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")
        request.user = AnonymousUser()
        UserTimezoneMiddleware(respond)(request)
        self.assertEqual(observed[-1], timezone.get_default_timezone_name())

    def test_webhook_rejects_redirects_instead_of_forwarding_credentials(self):
        handler = next(
            h for h in webhooks._opener.handlers if isinstance(h, webhooks.NoRedirect)
        )
        request = URLRequest(
            "https://receiver.test/hook",
            data=b"private",
            headers={"X-BabyBuddy-Signature": "private"},
        )
        self.assertIsNone(
            handler.redirect_request(
                request, Mock(), 302, "Redirect", {}, "https://other.test/"
            )
        )
        with self.assertRaises(HTTPError):
            webhooks._opener.error(
                "http",
                request,
                Mock(),
                302,
                "Redirect",
                {"location": "https://other.test/"},
            )

    def test_webhook_urls_and_failure_logs_do_not_expose_credentials(self):
        with patch.object(webhooks._opener, "open") as opened:
            for url in (
                "file:///etc/passwd",
                "ftp://example.test/",
                "https://user:secret@example.test/",
                "https://example.test/\r\nx:bad",
            ):
                with self.assertLogs("core.webhooks", level="WARNING"):
                    webhooks.send(url, {"event": "note.created"})
            opened.assert_not_called()
        secret_url = "https://receiver.test/hook?token=private-token"
        with patch.object(webhooks._opener, "open", side_effect=OSError(secret_url)):
            with self.assertLogs("core.webhooks", level="WARNING") as logs:
                webhooks.send(secret_url, {"event": "note.created"})
        self.assertNotIn("private-token", " ".join(logs.output))

    def test_webhooks_only_send_committed_events(self):
        set_setting_value("core.models", "Child", "url", "http://receiver.test/hook")
        try:
            with patch("core.webhooks.deliver_async") as deliver:
                with self.captureOnCommitCallbacks(execute=True):
                    with transaction.atomic():
                        models.Note.objects.create(
                            child=self.child, note="rolled back", time=timezone.now()
                        )
                        transaction.set_rollback(True)
                deliver.assert_not_called()
                with self.captureOnCommitCallbacks(execute=True):
                    models.Note.objects.create(
                        child=self.child, note="committed", time=timezone.now()
                    )
                    deliver.assert_not_called()
                deliver.assert_called_once()
                self.assertEqual(deliver.call_args.args[1]["data"]["note"], "committed")
        finally:
            set_setting_value("core.models", "Child", "url", "")

    def test_webhook_work_is_bounded_and_slots_are_released(self):
        with patch("core.webhooks._pending") as slots, patch(
            "core.webhooks._executor"
        ) as executor:
            slots.acquire.return_value = False
            with self.assertLogs("core.webhooks", level="WARNING"):
                webhooks.deliver_async(
                    "http://receiver.test/", {"event": "note.created"}
                )
            executor.submit.assert_not_called()
            slots.acquire.return_value = True
            webhooks.deliver_async("http://receiver.test/", {"event": "note.created"})
            callback = executor.submit.return_value.add_done_callback.call_args.args[0]
            callback(None)
            slots.release.assert_called_once()
