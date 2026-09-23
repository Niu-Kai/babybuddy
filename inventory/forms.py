import uuid
from django import forms
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from babybuddy.widgets import DateInput
from .models import (
    StockItem,
    StockMovement,
    ChildSupplyProfile,
    CLOTHING_SIZES,
)


class ItemForm(forms.ModelForm):
    starting_quantity = forms.DecimalField(
        label=_("Quantity on hand"),
        min_value=0,
        max_digits=12,
        decimal_places=3,
        initial=0,
    )

    class Meta:
        model = StockItem
        fields = [
            "name",
            "category",
            "size",
            "stage",
            "unit",
            "expiration_date",
            "min_age_months",
            "max_age_months",
            "notes",
        ]
        widgets = {
            "size": forms.TextInput(
                attrs={
                    "list": "diaper-sizes",
                    "placeholder": _("Choose a package weight range or type a size"),
                }
            ),
            "expiration_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "name": _("Name"),
            "category": _("Category"),
            "size": _("Size"),
            "stage": _("Stage"),
            "unit": _("Stock unit"),
            "notes": _("Notes"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("starting_quantity")
            self.fields["unit"].disabled = True

    def clean(self):
        cleaned = super().clean()
        value = cleaned.get("starting_quantity")
        if (
            value is not None
            and cleaned.get("unit") not in {"mL", "fl oz", "g", "oz"}
            and value != value.to_integral_value()
        ):
            self.add_error("starting_quantity", _("Use a whole number for this unit."))
        return cleaned

    def sections(self):
        groups = [
            (
                _("Item"),
                [
                    "name",
                    "category",
                    "size",
                    "stage",
                    "unit",
                    "starting_quantity",
                ],
            ),
            (
                _("Optional details"),
                ["expiration_date", "min_age_months", "max_age_months", "notes"],
            ),
        ]
        return [
            (name, [self[key] for key in keys if key in self.fields])
            for name, keys in groups
        ]


class MovementForm(forms.Form):
    action = forms.ChoiceField(
        label=_("Action"),
        choices=[
            ("use", _("Use stock")),
            ("add", _("Restock")),
            ("set", _("Correct count")),
        ],
    )
    amount = forms.DecimalField(min_value=0, max_digits=12, decimal_places=3)
    note = forms.CharField(label=_("Note"), required=False, max_length=160)
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def __init__(self, *args, item, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)
        self.fields["amount"].label = _("Quantity (%(unit)s)") % {"unit": item.unit}

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if amount is not None:
            if cleaned.get("action") != "set" and amount <= 0:
                self.add_error("amount", _("Enter a quantity greater than zero."))
            if (
                self.item.unit not in {"mL", "fl oz", "g", "oz"}
                and amount != amount.to_integral_value()
            ):
                self.add_error("amount", _("Use a whole number for this unit."))
        return cleaned

    @transaction.atomic
    def apply(self, user):
        from django.core.exceptions import ValidationError
        from django.db.models import F

        data = self.cleaned_data
        item = StockItem.objects.select_for_update().get(pk=self.item.pk)
        previous = StockMovement.objects.filter(token=data["token"]).first()
        if previous:
            if previous.item_id != item.pk:
                raise ValidationError(_("This stock update has already been used."))
            return
        if item.archived:
            raise ValidationError(_("Restore this item before changing stock."))
        amount, action = data["amount"], data["action"]
        if action == "add" and item.expired:
            raise ValidationError(
                _("This batch is expired. Add a new inventory item for the new batch.")
            )
        change = (
            amount
            if action == "add"
            else -amount if action == "use" else amount - item.quantity
        )
        if item.quantity + change < 0:
            raise ValidationError(
                _("There is not enough stock. Correct the count if needed.")
            )
        if item.quantity + change > 999999999:
            raise ValidationError(_("The resulting quantity is too large."))
        updated = StockItem.objects.filter(pk=item.pk, quantity=item.quantity).update(
            quantity=F("quantity") + change,
            snoozed_until=None,
            updated_at=timezone.now(),
        )
        if not updated:
            raise ValidationError(
                _("Stock changed while you were editing. Refresh and try again.")
            )
        StockMovement.objects.create(
            item=item,
            token=data["token"],
            action=action,
            change=change,
            balance=item.quantity + change,
            user=user,
            note=data["note"],
        )


class DiaperSupplyChoice(forms.ModelChoiceField):
    def label_from_instance(self, item):
        size = item.size or _("Size not set")
        return f"{item.name} · {size} · {item.quantity:g} {item.unit}"


class SizeForm(forms.ModelForm):
    diaper_stock = DiaperSupplyChoice(
        queryset=StockItem.objects.none(),
        required=False,
        label=_("Diaper supply"),
        empty_label=_("Automatic — matching size or age range"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["diaper_stock"].queryset = StockItem.objects.filter(
            category="diapers",
            unit__in=["diapers", "items"],
            archived=False,
            stage="current",
        ).order_by("name", "size", "pk")

    def clean(self):
        from .diapers import supply_available

        cleaned = super().clean()
        item = cleaned.get("diaper_stock")
        self.instance.diaper_size = cleaned.get("diaper_size", "")
        if item and not supply_available(item):
            self.add_error(
                "diaper_stock",
                _("Choose an available diaper supply."),
            )
        if item and "diaper_stock" not in self.errors:
            cleaned["diaper_size"] = item.size
        return cleaned

    class Meta:
        model = ChildSupplyProfile
        fields = ["diaper_size", "auto_deduct_diapers", "diaper_stock", "clothing_size"]
        labels = {
            "diaper_size": _("Diaper size / weight range"),
            "clothing_size": _("Clothing size"),
        }
        widgets = {
            "diaper_size": forms.TextInput(
                attrs={
                    "list": "diaper-sizes",
                    "placeholder": _("Choose a package weight range or type a size"),
                }
            ),
            "clothing_size": forms.TextInput(attrs={"list": "clothing-sizes"}),
        }


class EquipmentForm(forms.ModelForm):
    hide_field_help = True

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        from core.access import scoped
        from core.models import Child

        self.fields["children"].queryset = scoped(Child.objects.all(), self.user)
        # Preserve assignments the editor is not allowed to view.
        from core.access import unscoped

        with unscoped():
            self.hidden_children = (
                list(
                    self.instance.children.exclude(
                        pk__in=self.fields["children"].queryset
                    ).values_list("pk", flat=True)
                )
                if self.instance.pk
                else []
            )

    def _save_m2m(self):
        super()._save_m2m()
        if self.hidden_children:
            self.instance.children.add(*self.hidden_children)

    class Meta:
        from .models import Equipment

        model = Equipment
        fields = [
            "name",
            "children",
            "weight_limit",
            "weight_unit",
            "height_limit",
            "height_unit",
            "instructions",
            "manual_review",
            "archived",
        ]
        labels = {
            "name": _("Name"),
            "children": _("Children"),
            "weight_unit": _("Weight unit"),
            "height_unit": _("Height unit"),
            "archived": _("Archived"),
        }
        widgets = {
            "children": forms.CheckboxSelectMultiple,
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }
