from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


def grant_permissions(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission

    for role, actions in (
        ("READ_ONLY_GROUP_NAME", ("view",)),
        ("CAREGIVER_GROUP_NAME", ("view", "add", "change")),
    ):
        group = Group.objects.filter(name=settings.BABY_BUDDY[role]).first()
        if group:
            group.permissions.add(
                *Permission.objects.filter(
                    content_type__app_label="prebirth",
                    codename__in=[
                        f"{action}_{model}"
                        for action in actions
                        for model in ("plan", "checklistitem", "contraction")
                        if not (model == "plan" and action == "add")
                    ],
                )
            )


class PrebirthConfig(AppConfig):
    name = "prebirth"

    def ready(self):
        post_migrate.connect(grant_permissions, dispatch_uid="prebirth.roles")
