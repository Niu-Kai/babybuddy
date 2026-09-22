import uuid
from django import forms
from django.db import transaction
from django.utils import timezone
from babybuddy.widgets import DateInput
from .models import (
    StockItem,
    StockMovement,
    ChildSupplyProfile,
    CLOTHING_SIZES,
)


class ItemForm(forms.ModelForm):
    starting_quantity = forms.DecimalField(
        label="Quantity on hand",
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
                    "placeholder": "Choose a package weight range or type a size",
                }
            ),
            "expiration_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"unit": "Stock unit"}

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
            self.add_error("starting_quantity", "Use a whole number for this unit.")
        return cleaned

    def sections(self):
        groups = [
            (
                "Item",
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
                "Optional details",
                ["expiration_date", "min_age_months", "max_age_months", "notes"],
            ),
        ]
        return [
            (name, [self[key] for key in keys if key in self.fields])
            for name, keys in groups
        ]


class MovementForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("use", "Use stock"), ("add", "Restock"), ("set", "Correct count")]
    )
    amount = forms.DecimalField(min_value=0, max_digits=12, decimal_places=3)
    note = forms.CharField(required=False, max_length=160)
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def __init__(self, *args, item, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)
        self.fields["amount"].label = f"Quantity ({item.unit})"

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if amount is not None:
            if cleaned.get("action") != "set" and amount <= 0:
                self.add_error("amount", "Enter a quantity greater than zero.")
            if (
                self.item.unit not in {"mL", "fl oz", "g", "oz"}
                and amount != amount.to_integral_value()
            ):
                self.add_error("amount", "Use a whole number for this unit.")
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
                raise ValidationError("This stock update has already been used.")
            return
        if item.archived:
            raise ValidationError("Restore this item before changing stock.")
        amount, action = data["amount"], data["action"]
        if action == "add" and item.expired:
            raise ValidationError(
                "This batch is expired. Add a new inventory item for the new batch."
            )
        change = (
            amount
            if action == "add"
            else -amount if action == "use" else amount - item.quantity
        )
        if item.quantity + change < 0:
            raise ValidationError(
                "There is not enough stock. Correct the count if needed."
            )
        if item.quantity + change > 999999999:
            raise ValidationError("The resulting quantity is too large.")
        updated = StockItem.objects.filter(pk=item.pk, quantity=item.quantity).update(
            quantity=F("quantity") + change,
            snoozed_until=None,
            updated_at=timezone.now(),
        )
        if not updated:
            raise ValidationError(
                "Stock changed while you were editing. Refresh and try again."
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
        size = item.size or "Size not set"
        return f"{item.name} · {size} · {item.quantity:g} {item.unit}"


class SizeForm(forms.ModelForm):
    diaper_stock = DiaperSupplyChoice(
        queryset=StockItem.objects.none(),
        required=False,
        label="Diaper supply",
        empty_label="Automatic — matching size or age range",
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
                "Choose an available diaper supply.",
            )
        if item and "diaper_stock" not in self.errors:
            cleaned["diaper_size"] = item.size
        return cleaned

    class Meta:
        model = ChildSupplyProfile
        fields = ["diaper_size", "auto_deduct_diapers", "diaper_stock", "clothing_size"]
        labels = {"diaper_size": "Diaper size / weight range"}
        widgets = {
            "diaper_size": forms.TextInput(
                attrs={
                    "list": "diaper-sizes",
                    "placeholder": "Choose a package weight range or type a size",
                }
            ),
            "clothing_size": forms.TextInput(attrs={"list": "clothing-sizes"}),
        }
