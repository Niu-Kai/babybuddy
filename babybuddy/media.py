"""Permission-checked local images, including ImageKit thumbnails."""

from pathlib import PurePosixPath
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views import View
from api.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from babybuddy.models import access_expired


@method_decorator(never_cache, name="dispatch")
class PrivateMedia(View):
    def get(self, request, path):
        user = request.user
        if not user.is_authenticated:
            try:
                authenticated = TokenAuthentication().authenticate(request)
            except AuthenticationFailed:
                authenticated = None
            user = authenticated[0] if authenticated else None
        if not user or not user.is_active or access_expired(user):
            raise PermissionDenied
        if (
            "\\" in path
            or "\x00" in path
            or path.startswith("/")
            or ".." in PurePosixPath(path).parts
        ):
            raise Http404
        source = path
        cache_prefix = (
            getattr(settings, "IMAGEKIT_CACHEFILE_DIR", "CACHE/images").strip("/") + "/"
        )
        if source.startswith(cache_prefix):
            source = source[len(cache_prefix) :]
        if source.startswith("child/picture/"):
            permission = "core.view_child"
        elif source.startswith("notes/images/"):
            permission = "core.view_note"
        else:
            raise Http404
        if not user.has_perm(permission):
            raise PermissionDenied
        from core.access import restricted, scoped

        if restricted(user):
            from core.models import Child, Note

            model, field = (
                (Child, "picture")
                if permission == "core.view_child"
                else (Note, "image")
            )
            permitted = scoped(model.objects.all(), user).exclude(**{field: ""})
            names = permitted.values_list(field, flat=True)
            if not any(
                name
                and (source == name or source.startswith(name.rsplit(".", 1)[0] + "/"))
                for name in names
            ):
                raise Http404
        types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".avif": "image/avif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }
        content_type = types.get(PurePosixPath(path).suffix.lower())
        if not content_type:
            raise Http404
        try:
            image = default_storage.open(path, "rb")
        except (FileNotFoundError, OSError):
            raise Http404
        response = FileResponse(image, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
