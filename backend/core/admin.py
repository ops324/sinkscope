from django.contrib import admin

from .models import (
    DisplacementVelocity,
    GroundClass,
    MeshCell,
    PrecipitationObservation,
    RoadExposure,
    SubsidenceEvent,
)


@admin.register(MeshCell)
class MeshCellAdmin(admin.ModelAdmin):
    search_fields = ["mesh_code"]


@admin.register(DisplacementVelocity)
class DisplacementVelocityAdmin(admin.ModelAdmin):
    list_display = ["mesh_cell", "fiscal_year", "velocity_cm_per_year", "source"]
    list_filter = ["fiscal_year", "source"]


@admin.register(GroundClass)
class GroundClassAdmin(admin.ModelAdmin):
    list_display = ["mesh_cell", "geology_class", "ground_classification", "land_use_class"]
    list_filter = ["geology_class", "ground_classification", "land_use_class"]


@admin.register(PrecipitationObservation)
class PrecipitationObservationAdmin(admin.ModelAdmin):
    list_display = ["mesh_cell", "period_start", "period_end", "accumulated_mm", "source"]


@admin.register(RoadExposure)
class RoadExposureAdmin(admin.ModelAdmin):
    list_display = ["mesh_cell", "road_length_m", "source"]


@admin.register(SubsidenceEvent)
class SubsidenceEventAdmin(admin.ModelAdmin):
    list_display = ["location_text", "fiscal_year", "prefecture", "cause_facility", "mesh_cell", "geocode_confidence"]
    list_filter = ["prefecture", "fiscal_year", "cause_facility", "road_jurisdiction", "geocode_confidence"]
