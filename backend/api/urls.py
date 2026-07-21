from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("mesh/summary/", views.mesh_summary, name="mesh-summary"),
    path("events/", views.events, name="events"),
    path("analysis/run/latest/", views.analysis_run_latest, name="analysis-run-latest"),
]
