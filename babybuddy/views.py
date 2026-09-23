# -*- coding: utf-8 -*-
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LogoutView as LogoutViewBase
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import BadRequest
from django.forms import Form
from django.http import HttpResponse, HttpResponseForbidden
from django.middleware.csrf import REASON_BAD_ORIGIN
from django.shortcuts import redirect, render
from django.template import loader
from django.urls import reverse, reverse_lazy
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.text import format_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views import csrf
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import View
from django.views.generic.base import TemplateView, RedirectView
from django.views.generic.detail import BaseDetailView
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    FormMixin,
    SingleObjectTemplateResponseMixin,
    UpdateView,
)
from django.views.i18n import set_language

from axes.utils import reset
from django_filters.views import FilterView

from babybuddy import forms
from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin, StaffOnlyMixin


def csrf_failure(request, reason=""):
    """
    Overrides the 403 CSRF failure template for bad origins in order to provide more
    useful information about how to resolve the issue.
    """

    if (
        "HTTP_ORIGIN" in request.META
        and reason == REASON_BAD_ORIGIN % request.META.get("HTTP_ORIGIN")
    ):
        context = {
            "title": _("Forbidden"),
            "main": _("CSRF verification failed. Request aborted."),
            "reason": reason,
            "origin": request.META.get("HTTP_ORIGIN"),
        }
        template = loader.get_template("error/403_csrf_bad_origin.html")
        return HttpResponseForbidden(template.render(context), content_type="text/html")

    return csrf.csrf_failure(request, reason, "403_csrf.html")


class RootRouter(LoginRequiredMixin, RedirectView):
    """
    Redirects to the site dashboard.
    """

    def get_redirect_url(self, *args, **kwargs):
        self.url = reverse("dashboard:dashboard")
        return super(RootRouter, self).get_redirect_url(self, *args, **kwargs)


class BabyBuddyFilterView(FilterView):
    """
    Disables "strictness" for django-filter. It is unclear from the
    documentation exactly what this does...
    """

    # TODO Figure out the correct way to use this.
    strict = False

    def get_queryset(self):
        from core.presentation import presentation
        from django.db.models import DateTimeField, DateField, OuterRef, Subquery, Q

        queryset = super().get_queryset()
        fields = {field.name: field for field in self.model._meta.fields}
        if "child" not in fields:
            return queryset
        self.record_model_name = self.model._meta.model_name
        if self.record_model_name == "headcircumference":
            self.record_model_name = "head-circumference"
        scope = presentation(self.request)
        if scope["selected_child"] and self.model._meta.model_name != "pumping":
            queryset = queryset.filter(child=scope["selected_child"])
        queryset = queryset.select_related("child")
        if "created_by" in fields:
            queryset = queryset.select_related("created_by")
        if self.model._meta.model_name == "bmi":
            queryset = queryset.select_related("source_weight", "source_height")
        elif hasattr(self.model, "tags"):
            queryset = queryset.prefetch_related("tags")
        if "user" in fields:
            queryset = queryset.select_related("user")
        if self.model._meta.model_name == "feeding":
            queryset = queryset.prefetch_related("foods")
            # Correlated lookup works across page boundaries and never compares
            # different children, even in the combined household view.
            previous = (
                self.model.objects.filter(child_id=OuterRef("child_id"))
                .filter(
                    Q(start__lt=OuterRef("start"))
                    | Q(start=OuterRef("start"), pk__lt=OuterRef("pk"))
                )
                .order_by("-start", "-pk")
            )
            queryset = queryset.annotate(
                previous_feeding_start=Subquery(previous.values("start")[:1])
            )
        if self.model._meta.model_name == "pumping":
            previous = self.model.objects.filter(
                Q(start__lt=OuterRef("start"))
                | Q(start=OuterRef("start"), pk__lt=OuterRef("pk"))
            ).order_by("-start", "-pk")
            queryset = queryset.annotate(
                previous_pumping_start=Subquery(previous.values("start")[:1])
            )
        if self.model._meta.model_name in {"sleep", "diaperchange", "tummytime"}:
            start_field = "start" if "start" in fields else "time"
            previous_field = "end" if "end" in fields else "time"
            previous = (
                self.model.objects.filter(child_id=OuterRef("child_id"))
                .filter(
                    Q(**{start_field + "__lt": OuterRef(start_field)})
                    | Q(
                        **{start_field: OuterRef(start_field), "pk__lt": OuterRef("pk")}
                    )
                )
                .order_by("-" + start_field, "-pk")
            )
            queryset = queryset.annotate(
                previous_entry_end=Subquery(previous.values(previous_field)[:1])
            )
        date_field = next(
            (
                name
                for name in ("start", "time", "date")
                if name in fields
                and isinstance(fields[name], (DateTimeField, DateField))
            ),
            None,
        )
        if date_field:
            from core.forms import RecordPeriodFilterForm
            from datetime import date

            self.record_period = RecordPeriodFilterForm(
                self.request.GET, user=self.request.user
            )
            if not self.record_period.is_valid():
                return queryset.none()
            name = date_field + (
                "__date" if isinstance(fields[date_field], DateTimeField) else ""
            )
            first = self.record_period.cleaned_data.get("range_start")
            last = self.record_period.cleaned_data.get("range_end")
            if first:
                queryset = queryset.filter(
                    **{name + "__gte": first, name + "__lte": last}
                )
            elif "period" not in self.request.GET:
                # Keep existing bookmarked date-range links working.
                for parameter, lookup in (("from", "gte"), ("to", "lte")):
                    try:
                        value = date.fromisoformat(self.request.GET.get(parameter, ""))
                    except ValueError:
                        continue
                    queryset = queryset.filter(**{name + "__" + lookup: value})
        return queryset

    def get_filterset_kwargs(self, filterset_class):
        from core.presentation import presentation

        kwargs = super().get_filterset_kwargs(filterset_class)
        if any(field.name == "child" for field in self.model._meta.fields):
            data = self.request.GET.copy()
            if (
                "scope" in data
                or presentation(self.request)["side_by_side"]
                or presentation(self.request)["selected_child"]
            ):
                data.pop("child", None)
            kwargs["data"] = data
        return kwargs

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        from core.presentation import presentation

        context = super().get_context_data(**kwargs)
        if not hasattr(self, "record_model_name"):
            return context
        from core.units import SPECS, preferred_unit

        spec = SPECS.get(self.model._meta.model_name)
        if spec:
            unit_key = "display_unit_" + self.model._meta.model_name
            allowed = {unit for unit, _ in spec[3]} | {"original"}
            requested = self.request.GET.get("unit")
            if requested in allowed:
                self.request.session[unit_key] = requested
            default = preferred_unit(
                self.request.user.settings, self.model._meta.model_name
            )
            context["display_unit"] = self.request.session.get(unit_key, default)
            if context["display_unit"] not in allowed:
                context["display_unit"] = default
            context["unit_choices"] = [("original", _("As entered"))] + list(spec[3])
            context["unrecorded_units"] = self.filterset.qs.filter(
                entry_unit=""
            ).exists()
        context["record_model_name"] = self.record_model_name
        context["record_add_permission"] = (
            self.model._meta.model_name != "bmi"
            and self.request.user.has_perm("core.add_" + self.model._meta.model_name)
        )
        scope = presentation(self.request)
        context["unique_child"] = bool(scope["selected_child"])
        context["record_count"] = (
            context["paginator"].count
            if context.get("paginator")
            else self.filterset.qs.count()
        )
        if hasattr(self, "record_period"):
            from django.utils import timezone

            context["record_period"] = self.record_period
            context["today"] = timezone.localdate()
            context["record_range_start"] = self.record_period.cleaned_data.get(
                "range_start"
            )
            context["record_range_end"] = self.record_period.cleaned_data.get(
                "range_end"
            )
            context["extra_filters_active"] = any(
                self.request.GET.get(name)
                for name in context["filter"].form.fields
                if name != "child"
            )
        context["filter"].form.fields.pop("child", None)
        if scope["side_by_side"] and self.model._meta.model_name != "pumping":
            panels = []
            for child in scope["scope_children"]:
                query = self.filterset.qs.filter(child=child)
                pager = Paginator(query, self.get_paginate_by(query))
                key = f"page_child_{child.pk}"
                panels.append(
                    {
                        "child": child,
                        "page": pager.get_page(self.request.GET.get(key)),
                        "page_key": key,
                    }
                )
            if (
                self.model._meta.model_name == "timer"
                and self.filterset.qs.filter(child__isnull=True).exists()
            ):
                pager = Paginator(
                    self.filterset.qs.filter(child__isnull=True),
                    self.get_paginate_by(self.filterset.qs),
                )
                panels.append(
                    {
                        "child": None,
                        "page": pager.get_page(self.request.GET.get("page_unassigned")),
                        "page_key": "page_unassigned",
                    }
                )
            context["record_panels"] = panels
        return context


class BabyBuddyPaginatedView(View):
    def get_paginate_by(self, queryset):
        return self.request.user.settings.pagination_count


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(never_cache, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class LogoutView(LogoutViewBase):
    pass


class UserList(StaffOnlyMixin, BabyBuddyFilterView):
    model = get_user_model()
    template_name = "babybuddy/user_list.html"
    ordering = "username"
    paginate_by = 10
    filterset_fields = ("username", "first_name", "last_name", "email")


class UserAdd(StaffOnlyMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = get_user_model()
    template_name = "babybuddy/user_form.html"
    permission_required = ("admin.add_user",)
    form_class = forms.UserAddForm
    success_url = reverse_lazy("babybuddy:user-list")
    success_message = gettext_lazy("User %(username)s added!")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class UserUpdate(
    StaffOnlyMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView
):
    model = get_user_model()
    template_name = "babybuddy/user_form.html"
    permission_required = ("admin.change_user",)
    form_class = forms.UserUpdateForm
    success_url = reverse_lazy("babybuddy:user-list")
    success_message = gettext_lazy("User %(username)s updated.")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class UserUnlock(
    StaffOnlyMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    FormMixin,
    SingleObjectTemplateResponseMixin,
    BaseDetailView,
):
    model = get_user_model()
    template_name = "babybuddy/user_confirm_unlock.html"
    permission_required = ("admin.change_user",)
    form_class = Form
    success_message = gettext_lazy("User unlocked.")

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        form = self.get_form()
        if form.is_valid():
            reset(username=user.username)
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("babybuddy:user-update", kwargs={"pk": self.kwargs["pk"]})


class UserDelete(
    StaffOnlyMixin, PermissionRequiredMixin, DeleteView, SuccessMessageMixin
):
    model = get_user_model()
    template_name = "babybuddy/user_confirm_delete.html"
    permission_required = ("admin.delete_user",)
    success_url = reverse_lazy("babybuddy:user-list")

    def get_success_message(self, cleaned_data):
        return format_lazy(gettext_lazy("User {user} deleted."), user=self.get_object())


class UserPassword(LoginRequiredMixin, View):
    """
    Handles user password changes.
    """

    form_class = forms.UserPasswordForm
    template_name = "babybuddy/user_password_form.html"

    def get(self, request):
        return render(
            request, self.template_name, {"form": self.form_class(request.user)}
        )

    def post(self, request):
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, _("Password updated."))
        return render(request, self.template_name, {"form": form})


def handle_api_regenerate_request(request) -> bool:
    """
    Checks if the current request contains a request to update the API key
    and if it does, updeates the API key.

    Returns True, if the API-key regenerate request was detected and handled.
    """

    if "api_key_regenerate" in request.POST:
        request.user.settings.api_key(reset=True)
        messages.success(request, _("User API key regenerated."))
        return True
    return False


class UserSettings(LoginRequiredMixin, View):
    """
    Handles both the User and Settings models.
    Based on this SO answer: https://stackoverflow.com/a/45056835.
    """

    form_user_class = forms.UserForm
    form_settings_class = forms.UserSettingsForm
    template_name = "babybuddy/user_settings_form.html"

    def get(self, request):
        settings = request.user.settings

        return render(
            request,
            self.template_name,
            {
                "form_user": self.form_user_class(instance=request.user),
                "form_settings": self.form_settings_class(instance=settings),
            },
        )

    def post(self, request):
        if handle_api_regenerate_request(request):
            return redirect("babybuddy:user-settings")

        form_user = self.form_user_class(instance=request.user, data=request.POST)
        form_settings = self.form_settings_class(
            instance=request.user.settings, data=request.POST
        )
        if form_user.is_valid() and form_settings.is_valid():
            user = form_user.save(commit=False)
            user_settings = form_settings.save(commit=False)
            user.settings = user_settings
            user.save()
            from core.units import UNIT_PREFERENCE_FIELDS

            for model, field in UNIT_PREFERENCE_FIELDS.items():
                if request.POST.get(field) and field in form_settings.changed_data:
                    request.session.pop("display_unit_" + model, None)
            translation.activate(user.settings.language)
            messages.success(request, _("Settings saved!"))
            translation.deactivate()
            return set_language(request)
        return render(
            request,
            self.template_name,
            {"form_user": form_user, "form_settings": form_settings},
        )


class UserAddDevice(LoginRequiredMixin, View):
    form_user_class = forms.UserForm
    template_name = "babybuddy/user_add_device.html"
    qr_code_template = "babybuddy/login_qr_code.txt"

    def get(self, request):
        # Assemble qr_code json-data. For Home Assistant ingress support, we
        # also need to extract the ingress_session token to allow an external
        # app to authenticate with home assistant so it can reach baby buddy
        session_cookies = {}
        if request.is_homeassistant_ingress_request:
            session_cookies["ingress_session"] = request.COOKIES.get("ingress_session")

        qr_code_response = render(
            request,
            self.qr_code_template,
            {"session_cookies": json.dumps(session_cookies)},
        )
        qr_code_data = qr_code_response.content.decode().strip()

        # Now that the qr_code json-data is assembled, we can pass the json
        # structure as data to the user_add_device - template where it will
        # be converted into a qr-code.
        return render(
            request,
            self.template_name,
            {
                "form_user": self.form_user_class(instance=request.user),
                "qr_code_data": qr_code_data,
            },
        )

    def post(self, request):
        if handle_api_regenerate_request(request):
            return redirect("babybuddy:user-add-device")
        else:
            raise BadRequest()


class Welcome(LoginRequiredMixin, TemplateView):
    """
    Basic introduction to Baby Buddy (meant to be shown when no data is in the
    database).
    """

    template_name = "babybuddy/welcome.html"


class ServiceWorker(View):
    """Keep the service worker scoped to this installation, including mount paths."""

    def get(self, request):
        from django.template.loader import render_to_string

        response = HttpResponse(
            render_to_string("babybuddy/sw.js"), content_type="application/javascript"
        )
        response["Service-Worker-Allowed"] = reverse("babybuddy:root-router")
        response["Cache-Control"] = "no-cache"
        return response


class ExportData(StaffOnlyMixin, View):
    """
    One-click export of every record as a zip of CSV files, one per model,
    using the same resources as the admin's per-model export (#124).
    """

    def get(self, request):
        import io
        import zipfile

        from django.contrib import admin as django_admin
        from django.http import HttpResponse
        from django.utils import timezone
        from import_export.resources import modelresource_factory

        from core import models as core_models

        exported = [
            core_models.Child,
            core_models.DiaperChange,
            core_models.Feeding,
            core_models.Pumping,
            core_models.Sleep,
            core_models.TummyTime,
            core_models.Temperature,
            core_models.Weight,
            core_models.Height,
            core_models.HeadCircumference,
            core_models.BMI,
            core_models.Medication,
            core_models.Note,
            core_models.Appointment,
            core_models.BathTime,
            core_models.Reflux,
            core_models.Food,
            core_models.CustomActivity,
            core_models.ActivityType,
            core_models.Tag,
        ]
        # Staff status alone does not authorize reading every model.
        from django.core.exceptions import PermissionDenied

        required = [f"core.view_{model._meta.model_name}" for model in exported]
        if not request.user.has_perms(required):
            raise PermissionDenied
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for model in exported:
                model_admin = django_admin.site._registry.get(model)
                resource_class = getattr(model_admin, "resource_class", None)
                if resource_class is None:
                    resource_class = modelresource_factory(model)
                dataset = resource_class().export()
                from babybuddy.exports import safe_csv

                archive.writestr(f"{model._meta.model_name}.csv", safe_csv(dataset))
        stamp = timezone.localdate().strftime("%Y%m%d")
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="babybuddy-export-{stamp}.zip"'
        )
        return response
