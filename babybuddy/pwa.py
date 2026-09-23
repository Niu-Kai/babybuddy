"""Public installation metadata scoped to this Django application's mount path."""

import json
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views import View


class AppManifest(View):
    def get(self, request):
        manifest = json.loads(
            (
                Path(settings.BASE_DIR) / "babybuddy/static_src/root/site.webmanifest"
            ).read_text(encoding="utf-8")
        )
        root = reverse("babybuddy:root-router")
        manifest.update(id=root, scope=root, start_url=root)
        for icon in manifest["icons"]:
            icon["src"] = static("babybuddy/root/" + icon["src"])
        for shortcut, route in zip(
            manifest["shortcuts"],
            ("timer", "diaperchange", "feeding", "pumping", "sleep", "tummytime"),
        ):
            shortcut["url"] = reverse("core:" + route + "-add")
        response = JsonResponse(manifest, content_type="application/manifest+json")
        response["Cache-Control"] = "no-cache"
        return response
