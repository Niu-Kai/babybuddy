from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


def grant_inventory_permissions(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission

    for setting, actions in [
        ("READ_ONLY_GROUP_NAME", ["view"]),
        ("CAREGIVER_GROUP_NAME", ["view", "add", "change"]),
    ]:
        group = Group.objects.filter(name=settings.BABY_BUDDY[setting]).first()
        if group:
            codes = [
                f"{action}_{model}"
                for action in actions
                for model in ("stockitem", "equipment")
            ] + [
                "view_stockmovement",
                "view_childsupplyprofile",
            ]
            group.permissions.add(
                *Permission.objects.filter(
                    content_type__app_label="inventory", codename__in=codes
                )
            )


class InventoryConfig(AppConfig):
    name = "inventory"

    def ready(self):
        from .diapers import connect

        connect()
        post_migrate.connect(
            grant_inventory_permissions, dispatch_uid="inventory.roles"
        )
