from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models

STORAGE_SRID = settings.SINKSCOPE_STORAGE_SRID


class MeshCell(models.Model):
    """全レイヤーの共通空間単位となる250mメッシュ。"""

    mesh_code = models.CharField(max_length=32, unique=True)
    geom = gis_models.PolygonField(srid=STORAGE_SRID)
    centroid = gis_models.PointField(srid=STORAGE_SRID)

    class Meta:
        indexes = [models.Index(fields=["mesh_code"])]

    def __str__(self):
        return self.mesh_code


class DisplacementVelocity(models.Model):
    """国土地理院 衛星SAR地盤変動測量成果による、メッシュ単位の準上下方向変位速度（実データ）。

    GSIが提供するのは各年度時点での「変位速度」（観測期間全体を通じた線形トレンド、
    cm/年）であり、稠密な多時点の累積変位量ではない。年度(fiscal_year)ごとに別行として
    保存することで、年度間の速度差（トレンド変化）を後段の解析で比較できるようにする。
    """

    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="displacement_velocities"
    )
    fiscal_year = models.CharField(max_length=8)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    velocity_cm_per_year = models.FloatField()
    source = models.CharField(max_length=64, default="gsi_sar_tsa")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mesh_cell", "fiscal_year", "source"],
                name="unique_displacement_velocity",
            )
        ]
        indexes = [models.Index(fields=["mesh_cell", "fiscal_year"])]
        ordering = ["mesh_cell_id", "fiscal_year"]


class GroundClass(models.Model):
    """国土数値情報由来の、メッシュ単位の地質・地盤・土地利用（実データ）。"""

    mesh_cell = models.OneToOneField(
        MeshCell, on_delete=models.CASCADE, related_name="ground_class"
    )
    geology_class = models.CharField(max_length=64, blank=True)
    ground_classification = models.CharField(max_length=64, blank=True)
    land_use_class = models.CharField(max_length=64, blank=True)
    elevation_m = models.FloatField(null=True, blank=True)
    source_year = models.PositiveSmallIntegerField(null=True, blank=True)


class PrecipitationObservation(models.Model):
    """メッシュ単位・期間単位の累積降水量（実データ）。"""

    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="precipitation_observations"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    accumulated_mm = models.FloatField()
    source = models.CharField(max_length=64)

    class Meta:
        indexes = [models.Index(fields=["mesh_cell", "period_start", "period_end"])]
        ordering = ["mesh_cell_id", "period_start"]


class RoadExposure(models.Model):
    """メッシュ内の道路延長。陥没報告密度の曝露オフセットに使う（実データ）。"""

    mesh_cell = models.OneToOneField(
        MeshCell, on_delete=models.CASCADE, related_name="road_exposure"
    )
    road_length_m = models.FloatField()
    source = models.CharField(max_length=64, default="osm")


class SubsidenceEvent(models.Model):
    """国土交通省公表の道路陥没事案。位置は地名からのジオコーディング（実データ）。"""

    mesh_cell = models.ForeignKey(
        MeshCell,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subsidence_events",
    )
    geom = gis_models.PointField(srid=STORAGE_SRID, null=True, blank=True)
    fiscal_year = models.CharField(max_length=8, blank=True)
    prefecture = models.CharField(max_length=32, blank=True)
    location_text = models.CharField(max_length=255)
    road_name = models.CharField(max_length=128, blank=True)
    road_administrator = models.CharField(max_length=64, blank=True)
    road_jurisdiction = models.CharField(max_length=16, blank=True)
    cause_facility = models.CharField(max_length=64, blank=True)
    depth_m = models.FloatField(null=True, blank=True)
    geocode_confidence = models.CharField(max_length=16, blank=True)
    source = models.CharField(max_length=64, default="mlit_kanbotsu")

    class Meta:
        indexes = [models.Index(fields=["mesh_cell"])]
