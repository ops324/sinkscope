from django.contrib import admin

from .models import AnalysisRun, MeshSummary


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "fiscal_year"]
    readonly_fields = ["created_at"]


@admin.register(MeshSummary)
class MeshSummaryAdmin(admin.ModelAdmin):
    list_display = [
        "mesh_cell",
        "run",
        "velocity_cm_per_year",
        "land_use_class",
        "road_length_m",
        "event_count",
        "sewer_event_count",
    ]
    list_filter = ["run", "land_use_class"]
