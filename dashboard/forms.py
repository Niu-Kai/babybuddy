from django import forms
from django.utils.translation import gettext_lazy as _
from babybuddy.models import DASHBOARD_CARDS
from dashboard.layout import GLANCE, TRENDS, MEASUREMENTS, allowed


class DashboardLayoutForm(forms.Form):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        hidden = set(user.settings.dashboard_hidden_cards or [])
        labels = dict(DASHBOARD_CARDS)
        for name, title, keys in (
            ("measurements", _("Beside the child's name"), MEASUREMENTS),
            ("care", _("Care panels"), GLANCE),
            ("trends", _("Trends and history"), TRENDS),
        ):
            choices = [(key, labels[key]) for key in keys if allowed(user, key)]
            self.fields[name] = forms.MultipleChoiceField(
                label=title,
                required=False,
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
            )
            self.initial[name] = [key for key, label in choices if key not in hidden]

    def save(self):
        shown = {key for values in self.cleaned_data.values() for key in values}
        available = {
            key for field in self.fields.values() for key, label in field.choices
        }
        hidden = set(self.user.settings.dashboard_hidden_cards or []) - available
        hidden.update(available - shown)
        self.user.settings.dashboard_hidden_cards = sorted(hidden)
        self.user.settings.save(update_fields=["dashboard_hidden_cards"])
