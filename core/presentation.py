"""Shared desktop child scope and navigation, independent of record mutations."""

from django.urls import reverse
from django.utils.translation import gettext as _


def presentation(request):
    if hasattr(request, "_presentation"):
        return request._presentation
    from core.models import Child

    user = request.user
    children = (
        list(Child.objects.order_by("first_name", "last_name", "pk"))
        if user.is_authenticated and user.has_perm("core.view_child")
        else []
    )
    by_slug = {child.slug: child for child in children}
    scope = request.session.get("child_scope", "all")
    explicit = request.GET.get("scope")
    match = getattr(request, "resolver_match", None)
    if explicit in {"all", "compare"} or explicit in by_slug:
        scope = explicit
        request.session["child_scope"] = scope
    elif scope not in {"all", "compare"} and scope not in by_slug:
        scope = "all"
        request.session.pop("child_scope", None)
    selected = by_slug.get(scope)
    # A directly linked child page identifies the visible child. Comparison
    # routes retain their explicit all-children scope.
    route_child = by_slug.get(match.kwargs.get("slug")) if match else None
    if route_child and explicit is None and scope != "compare":
        selected = route_child
        request.session["child_scope"] = route_child.slug
    result = {
        "scope_children": children,
        "selected_child": selected,
        "child_scope": selected.slug if selected else scope,
        "side_by_side": scope == "compare",
        "scope_label": (
            str(selected)
            if selected
            else (
                _("All children · side by side")
                if scope == "compare"
                else _("All children")
            )
        ),
    }
    request._presentation = result
    return result


def scope_url(request, scope):
    match = request.resolver_match
    params = request.GET.copy()
    for key in list(params):
        if key in {"child", "page", "scope"} or key.startswith("page_child_"):
            params.pop(key)
    params["scope"] = scope
    path = request.path
    if match and "slug" in match.kwargs:
        if match.namespace == "dashboard":
            path = reverse("dashboard:dashboard")
        elif match.namespace == "reports":
            if scope in {"all", "compare"}:
                path = request.path
            else:
                path = reverse(match.view_name, kwargs={**match.kwargs, "slug": scope})
        elif match.view_name == "core:child":
            path = reverse("core:timeline")
        else:
            path = reverse("core:child-list")
    elif match and (
        match.url_name.endswith("-update")
        or match.url_name.endswith("-delete")
        or match.url_name.endswith("-detail")
    ):
        # Switching context must never retarget an existing edit/delete form.
        path = reverse("dashboard:dashboard")
    return path + "?" + params.urlencode()


MEASUREMENTS = [
    (
        "Growth",
        [
            ("weight", "Weight"),
            ("height", "Height"),
            ("head-circumference", "Head circumference"),
            ("bmi", "BMI"),
        ],
    ),
    ("Other measurements", [("temperature", "Temperature")]),
]
ACTIVITIES = [
    ("Feeding", [("feeding", "Feedings"), ("pumping", "Pumping"), ("food", "Foods")]),
    (
        "Daily care",
        [
            ("sleep", "Sleep"),
            ("diaperchange", "Diaper changes"),
            ("tummytime", "Tummy time"),
            ("bathtime", "Bath time"),
        ],
    ),
    ("Health", [("medication", "Medication"), ("reflux", "Reflux")]),
    ("Notes", [("note", "Notes")]),
]


def navigation(request):
    from core.models import Timer

    if not request.user.is_authenticated:
        return {}
    context = presentation(request).copy()
    match = request.resolver_match
    household_page = bool(
        match
        and (
            (match.url_name or "").startswith("pumping")
            or match.url_name == "report-pumping-amounts-child"
            or match.namespace == "inventory"
        )
    )
    context["household_page"] = household_page
    user = request.user

    def groups(definitions, action):
        result = []
        for label, entries in definitions:
            items = []
            for key, name in entries:
                if action == "add" and key == "bmi":
                    continue
                model = key.replace("-", "")
                if user.has_perm(f"core.{action}_{model}"):
                    url = reverse(f"core:{key}-{'list' if action == 'view' else 'add'}")
                    child = context["selected_child"]
                    if action == "add" and child and key != "pumping":
                        from urllib.parse import urlencode

                        url += "?" + urlencode({"child": child.slug})
                    items.append(
                        {
                            "label": _(name),
                            "url": url,
                            "active": request.path.startswith(
                                reverse(f"core:{key}-list")
                            ),
                        }
                    )
            if items:
                result.append({"label": _(label), "items": items})
        return result

    context["measurement_menu"] = groups(MEASUREMENTS, "view")
    context["activity_menu"] = groups(ACTIVITIES, "view")
    context["measurement_active"] = any(
        item["active"]
        for group in context["measurement_menu"]
        for item in group["items"]
    )
    context["activity_active"] = any(
        item["active"] for group in context["activity_menu"] for item in group["items"]
    )
    context["add_menu"] = groups(
        ACTIVITIES + MEASUREMENTS + [("Planning", [("appointment", "Appointment")])],
        "add",
    )
    context["child_choices"] = [
        {
            "label": str(child),
            "url": scope_url(request, child.slug),
            "active": context["child_scope"] == child.slug,
        }
        for child in context["scope_children"]
    ]
    context["combined_url"] = scope_url(request, "all")
    context["compare_url"] = scope_url(request, "compare")
    context["nav_timers"] = (
        Timer.objects.select_related("child", "user").all()
        if user.has_perm("core.view_timer")
        else []
    )
    from inventory.views import reminders

    context["inventory_reminders"] = reminders(request)
    context["nav_reports_url"] = reverse("reports:home")
    if context["selected_child"]:
        context["nav_reports_url"] = reverse(
            "reports:report-list", args=[context["selected_child"].slug]
        )
    return context
