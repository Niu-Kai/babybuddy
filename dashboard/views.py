# -*- coding: utf-8 -*-
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.views.generic.base import TemplateView
from django.utils import timezone
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView

from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin
from core.models import Child
from dashboard.templatetags import cards
from dashboard.forms import DashboardLayoutForm


class Dashboard(LoginRequiredMixin, TemplateView):
    # TODO: Use .card-deck in this template once BS4 is finalized.
    template_name = "dashboard/dashboard.html"

    # Show the overall dashboard or a child dashboard if one Child instance.
    def get(self, request, *args, **kwargs):
        from core.presentation import presentation

        scope = presentation(request)
        if scope["selected_child"]:
            return HttpResponseRedirect(
                reverse(
                    "dashboard:dashboard-child", args=[scope["selected_child"].slug]
                )
            )
        children = len(scope["scope_children"])
        if children == 1:
            return HttpResponseRedirect(
                reverse(
                    "dashboard:dashboard-child", args=[scope["scope_children"][0].slug]
                )
            )
        return super(Dashboard, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        from core.presentation import presentation

        context["objects"] = sorted(
            presentation(self.request)["scope_children"],
            key=lambda child: (child.last_name, child.first_name, child.pk),
        )
        context["hidden_cards"] = (
            self.request.user.settings.dashboard_hidden_cards or []
        )
        context["today"] = timezone.localdate()
        from dashboard.layout import sections

        context["dashboard_sections"] = sections(self.request.user)
        return context


class ChildDashboard(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/child.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hidden_cards"] = (
            self.request.user.settings.dashboard_hidden_cards or []
        )
        context["today"] = timezone.localdate()
        from dashboard.layout import sections

        context["dashboard_sections"] = sections(self.request.user)
        return context


class ChildStatistics(PermissionRequiredMixin, DetailView):
    """
    The statistics card as a full page (babybuddy/babybuddy#1020).
    """

    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        card = cards.card_statistics({"request": self.request}, self.object)
        context["stats"] = card["stats"]
        return context


class DashboardCustomize(LoginRequiredMixin, FormView):
    template_name = "dashboard/customize.html"
    form_class = DashboardLayoutForm
    success_url = reverse_lazy("dashboard:dashboard")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "reorder":
            from dashboard.layout import GLANCE, TRENDS, allowed

            order = request.POST.getlist("order")
            available = [key for key in GLANCE + TRENDS if allowed(request.user, key)]
            if (
                not order
                or len(order) != len(set(order))
                or any(key not in available for key in order)
            ):
                return JsonResponse({"error": "Invalid panel order."}, status=400)
            request.user.settings.dashboard_card_order = order + [
                key for key in available if key not in order
            ]
            request.user.settings.save(update_fields=["dashboard_card_order"])
            return JsonResponse({"saved": True})
        if request.POST.get("action") == "reset":
            from babybuddy.models import default_hidden_dashboard_cards

            request.user.settings.dashboard_hidden_cards = (
                default_hidden_dashboard_cards()
            )
            request.user.settings.dashboard_card_order = []
            request.user.settings.save(
                update_fields=["dashboard_hidden_cards", "dashboard_card_order"]
            )
            return HttpResponseRedirect(self.success_url)
        return super().post(request, *args, **kwargs)
