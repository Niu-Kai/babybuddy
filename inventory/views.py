from datetime import timedelta
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    FormView,
    View,
)
from babybuddy.mixins import PermissionRequiredMixin
from core.models import Child
from .models import (
    StockItem,
    StockMovement,
    ChildSupplyProfile,
    DIAPER_SIZES,
    CLOTHING_SIZES,
)
from .forms import ItemForm, MovementForm, SizeForm
from .forecast import forecast_items


def permitted_items(user):
    return StockItem.objects.all()


def reminders(request):
    if not request.user.has_perm("inventory.view_stockitem"):
        return []
    return [item for item in forecast_items(request) if item.alert]


class InventoryList(PermissionRequiredMixin, ListView):
    permission_required = "inventory.view_stockitem"
    template_name = "inventory/list.html"
    context_object_name = "items"

    def get_queryset(self):
        query = self.request.GET.get("q", "").casefold()
        category = self.request.GET.get("category")
        archived = self.request.GET.get("view") == "archived"
        if archived:
            supplies = list(StockItem.objects.filter(archived=True).defer("notes"))
            for item in supplies:
                item._daily_use_rate = None
        else:
            supplies = forecast_items(self.request)
        items = [
            item
            for item in supplies
            if item.archived == archived
            and (not category or item.category == category)
            and (
                not query
                or query in item.name.casefold()
                or query in item.size.casefold()
            )
        ]
        view = self.request.GET.get("view", "all")
        if view == "shopping":
            items = [item for item in items if item.reminder]
        elif view in {"current", "next", "outgrown", "review"}:
            items = [item for item in items if item.fit == view]
        return items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            categories=StockItem.CATEGORIES,
            inventory_view=self.request.GET.get("view", "all"),
            views=[
                ("all", "All supplies"),
                ("shopping", "Shopping list"),
                ("current", "Use now"),
                ("next", "Next size / later"),
                ("outgrown", "Outgrown"),
                ("archived", "Archived"),
            ],
        )
        return context


class ItemAccess:
    def get_queryset(self):
        return permitted_items(self.request.user)


class ItemDetail(ItemAccess, PermissionRequiredMixin, DetailView):
    model = StockItem
    permission_required = "inventory.view_stockitem"
    template_name = "inventory/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object._daily_use_rate = next(
            (
                item.daily_use_rate
                for item in forecast_items(self.request)
                if item.pk == self.object.pk
            ),
            None,
        )
        context["movements"] = self.object.movements.select_related("user")[:30]
        return context


class ItemFormMixin:
    model = StockItem
    form_class = ItemForm
    template_name = "inventory/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title="Edit supply" if self.object else "Add supply",
            cancel_url=reverse("inventory:list"),
            diaper_sizes=DIAPER_SIZES,
            clothing_sizes=CLOTHING_SIZES,
        )
        return context

    def get_success_url(self):
        return reverse("inventory:detail", args=[self.object.pk])


class ItemAdd(ItemFormMixin, PermissionRequiredMixin, CreateView):
    permission_required = ("inventory.view_stockitem", "inventory.add_stockitem")

    @transaction.atomic
    def form_valid(self, form):
        form.instance.quantity = form.cleaned_data["starting_quantity"]
        response = super().form_valid(form)
        StockMovement.objects.create(
            item=self.object,
            action="set",
            change=self.object.quantity,
            balance=self.object.quantity,
            user=self.request.user,
            note="Starting stock",
        )
        messages.success(self.request, "Supply added.")
        return response


class ItemEdit(ItemAccess, ItemFormMixin, PermissionRequiredMixin, UpdateView):
    permission_required = ("inventory.view_stockitem", "inventory.change_stockitem")

    @transaction.atomic
    def form_valid(self, form):
        # Preserve stock changed by another caregiver while this details form was open.
        current = StockItem.objects.select_for_update().get(pk=form.instance.pk)
        form.instance.quantity = current.quantity
        form.instance.snoozed_until = current.snoozed_until
        form.instance.archived = current.archived
        messages.success(self.request, "Supply updated.")
        return super().form_valid(form)


class StockUpdate(PermissionRequiredMixin, FormView):
    permission_required = ("inventory.view_stockitem", "inventory.change_stockitem")
    form_class = MovementForm
    template_name = "inventory/form.html"

    def get_form_kwargs(self):
        self.item = get_object_or_404(
            permitted_items(self.request.user), pk=self.kwargs["pk"]
        )
        return {**super().get_form_kwargs(), "item": self.item}

    def get_initial(self):
        action = self.request.GET.get("action", "use")
        return {
            "action": action if action in {"use", "add", "set"} else "use",
            "amount": 1,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title=f"Update stock · {self.item.name}",
            stock_item=self.item,
            cancel_url=reverse("inventory:detail", args=[self.item.pk]),
        )
        return context

    def form_valid(self, form):
        try:
            form.apply(self.request.user)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Stock updated.")
        return redirect("inventory:detail", pk=self.item.pk)


class ItemAction(PermissionRequiredMixin, View):
    permission_required = ("inventory.view_stockitem", "inventory.change_stockitem")

    def post(self, request, pk):
        item = get_object_or_404(permitted_items(request.user), pk=pk)
        action = request.POST.get("action")
        if action in {"archive", "restore"}:
            item.archived = action == "archive"
            item.save(update_fields=["archived"])
        elif action in {"snooze", "unsnooze"}:
            item.snoozed_until = (
                timezone.localdate() + timedelta(days=7) if action == "snooze" else None
            )
            item.save(update_fields=["snoozed_until"])
        else:
            return HttpResponseBadRequest("Unknown inventory action.")
        return redirect("inventory:detail", pk=item.pk)


class ChildSizes(PermissionRequiredMixin, FormView):
    permission_required = (
        "core.view_child",
        "core.change_child",
        "inventory.change_childsupplyprofile",
    )
    form_class = SizeForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("core:child-list")

    def get_form_kwargs(self):
        self.child = get_object_or_404(Child, pk=self.kwargs["pk"])
        profile = ChildSupplyProfile.objects.filter(
            child=self.child
        ).first() or ChildSupplyProfile(child=self.child)
        return {**super().get_form_kwargs(), "instance": profile}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title=f"Sizes & diaper supply · {self.child}",
            diaper_sizes=DIAPER_SIZES,
            clothing_sizes=CLOTHING_SIZES,
            cancel_url=reverse("core:child-list"),
        )
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Sizes and diaper supply updated.")
        return super().form_valid(form)
