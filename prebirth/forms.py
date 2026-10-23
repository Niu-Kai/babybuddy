from django import forms
from .models import Plan, ChecklistItem


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ("due_date", "hospital", "contact", "phone", "notes")
        widgets = {
            "due_date": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "notes": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ("label", "category")
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }
