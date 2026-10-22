from django.urls import path

from planner import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/health/", views.health, name="health"),
    path("api/route/", views.route, name="route"),
]
