from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def query_url(context, key, value):
    query = context["request"].GET.copy()
    query[key] = value
    return "?" + query.urlencode()


@register.simple_tag
def entry_add_url(model_name, child=None):
    from urllib.parse import urlencode

    url = reverse("core:" + model_name + "-add")
    return url + ("?" + urlencode({"child": child.slug}) if child else "")


@register.simple_tag(takes_context=True)
def measurement(context, entry, field):
    from core.units import SPECS, convert, preferred_unit
    from django.utils.html import format_html
    from django.utils.translation import gettext as _

    value = getattr(entry, field, None)
    if value is None:
        return "—"
    spec = SPECS.get(entry._meta.model_name)
    if not spec or not entry.entry_unit:
        return format_html(
            '<span class="measurement-value">{}</span> <small class="text-body-secondary">{}</small>',
            f"{value:g}",
            _("unit not recorded"),
        )
    request = context.get("request")
    settings = getattr(getattr(request, "user", None), "settings", None)
    unit = context.get("display_unit") or preferred_unit(
        settings, entry._meta.model_name
    )
    if unit == "original":
        unit = entry.entry_unit
    label = dict(spec[3]).get(unit, unit)
    number = convert(value, spec[1], unit)
    return format_html(
        '<span class="measurement-value">{} {}</span>',
        f"{number:,.2f}".rstrip("0").rstrip("."),
        label,
    )


@register.simple_tag(takes_context=True)
def feeding_amount(context, entry):
    from django.utils.html import format_html

    if (
        not entry.entry_unit
        and entry.secondary_type
        and entry.secondary_amount is not None
    ):
        from django.utils.translation import gettext as _

        return format_html(
            '<span class="measurement-value">{}</span> <small class="text-body-secondary">{}</small>',
            entry.amount_display,
            _("unit not recorded"),
        )
    first = measurement(context, entry, "amount")
    if entry.secondary_type and entry.secondary_amount is not None:
        second = measurement(context, entry, "secondary_amount")
        total = measurement(context, entry, "total_amount")
        return format_html("{} + {} = {}", first, second, total)
    return first


@register.simple_tag(takes_context=True)
def volume_total(context, value, unit_known=True):
    from core.units import convert, preferred_unit
    from django.utils.translation import gettext as _

    if not unit_known:
        return f"{value:g} " + _("(unit not recorded)")
    unit = preferred_unit(context["request"].user.settings, "feeding")
    return f"{convert(value, 'mL', unit):.2f}".rstrip("0").rstrip(".") + " " + unit
