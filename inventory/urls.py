from django.urls import path
from . import views

app_name = "inventory"
urlpatterns = [
    path("equipment/", views.EquipmentList.as_view(), name="equipment"),
    path("equipment/add/", views.EquipmentAdd.as_view(), name="equipment-add"),
    path(
        "equipment/<int:pk>/edit/", views.EquipmentEdit.as_view(), name="equipment-edit"
    ),
    path("", views.InventoryList.as_view(), name="list"),
    path("add/", views.ItemAdd.as_view(), name="add"),
    path("<int:pk>/", views.ItemDetail.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ItemEdit.as_view(), name="edit"),
    path("<int:pk>/stock/", views.StockUpdate.as_view(), name="stock"),
    path("<int:pk>/action/", views.ItemAction.as_view(), name="action"),
    path("sizes/<int:pk>/", views.ChildSizes.as_view(), name="sizes"),
]
