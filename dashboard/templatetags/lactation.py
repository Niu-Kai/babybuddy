from django import template
from core.lactation import overview
from dashboard.layout import allowed

register = template.Library()


@register.inclusion_tag("dashboard/lactation.html", takes_context=True)
def household_lactation(context, always=False):
    request = context["request"]
    visible = allowed(request.user, "pumping_overview") and (
        always
        or "pumping_overview"
        not in (request.user.settings.dashboard_hidden_cards or [])
    )
    return {
        **(overview(request.user) if visible else {}),
        "visible": visible,
        "request": request,
        "perms": context["perms"],
    }
