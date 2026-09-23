"""Public interface catalogs contain no household or account data."""

from django.conf import settings
from django.http import Http404
from django.utils import translation
from django.views.i18n import JavaScriptCatalog


class InterfaceCatalog(JavaScriptCatalog):
    def get(self, request, language, *args, **kwargs):
        allowed = {code.lower(): code for code, label in settings.LANGUAGES}
        if language.lower() not in allowed:
            raise Http404
        with translation.override(allowed[language.lower()]):
            response = super().get(request, *args, **kwargs)
            response["Content-Language"] = translation.get_language()
            # Language is explicit in the URL, so browser caching cannot mix users.
            response["Cache-Control"] = "public, max-age=3600"
            return response
