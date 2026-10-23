from django.urls import path
from . import views

app_name = "prebirth"

urlpatterns = [
    path("", views.Preparation.as_view(), name="preparation"),
    path("contractions/", views.Contractions.as_view(), name="contractions"),
]
