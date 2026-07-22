from django.contrib import admin

from .models import MeshPriority, SyntheticPipe, TriageRun


@admin.register(TriageRun)
class TriageRunAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "seed"]
    readonly_fields = ["created_at"]


@admin.register(MeshPriority)
class MeshPriorityAdmin(admin.ModelAdmin):
    list_display = [
        "mesh_cell",
        "run",
        "tier",
        "priority_index",
        "velocity_cm_per_year",
        "road_length_m",
        "sewer_event_count",
        "pipe_count",
    ]
    list_filter = ["run", "tier"]


@admin.register(SyntheticPipe)
class SyntheticPipeAdmin(admin.ModelAdmin):
    list_display = ["id", "mesh_cell", "install_year", "pipe_material", "seed", "is_synthetic"]
    list_filter = ["pipe_material"]
