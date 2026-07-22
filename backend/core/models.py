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


class DisplacementAcquisition(models.Model):
    """GSI 衛星SAR変位速度APIへの1回の取得の監査記録（来歴の正）。

    GSIのAPIは常に「現在年度成果」のスナップショット1枚しか返さず、年度を選択できない
    （docs/SPEC.md §4.1）。そのためAPI応答やダウンロードしたGeoTIFFに固定の年度ラベルを
    付けることはできず、`fiscal_year`はあくまで best-effort のラベルに過ぎない。
    **`content_sha256`（取得したGeoTIFFバイト列のSHA-256）こそが真のヴィンテージ識別子**
    であり、同一ラスタの再取得は`content_sha256`で重複排除し、既存の年度ラベルを
    上書きしない（`ingest/gsi_displacement.py`参照）。

    `fiscal_year_provenance`は年度ラベルの信頼度を表す：
    - "filename": execCommand応答のfile_name/zip_pathまたはZIP内エントリ名から一意に
      導出できた場合（現状、実際のファイル名フォーマットが未観測のため未実装。
      `ingest/gsi_displacement.py::_derive_fiscal_year`はフォーマット確認まで凍結している）。
    - "operator_override": 呼び出し側が年度を明示指定した場合。
    - "unverified_retrieval_time": 上記いずれも不能で、取得時点の日本の年度（4月〜翌3月）
      を推定値として代入した場合。GSIの成果公開には数か月単位のラグがあるため、
      取得時計の年度が実際の成果年度と一致する保証はない。
    """

    content_sha256 = models.CharField(max_length=64, unique=True)
    retrieved_at = models.DateTimeField()
    fiscal_year = models.CharField(max_length=8)
    fiscal_year_provenance = models.CharField(max_length=32)
    api_file_name = models.CharField(max_length=255, blank=True)
    zip_path = models.CharField(max_length=255, blank=True)
    tif_name = models.CharField(max_length=255, blank=True)
    bbox = models.JSONField()
    raw_file_info = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=64, default="gsi_sar_tsa")

    class Meta:
        ordering = ["-retrieved_at"]

    def __str__(self):
        return f"{self.fiscal_year} ({self.fiscal_year_provenance}) {self.content_sha256[:12]}"


class DisplacementVelocity(models.Model):
    """国土地理院 衛星SAR地盤変動測量成果による、メッシュ単位の準上下方向変位速度（実データ）。

    GSIが提供するのは各年度時点での「変位速度」（観測期間全体を通じた線形トレンド、
    cm/年）であり、稠密な多時点の累積変位量ではない。年度(fiscal_year)ごとに別行として
    保存することで、年度間の速度差（トレンド変化）を後段の解析で比較できるようにする。

    `fiscal_year`はラベルに過ぎず、真のヴィンテージ識別子は`acquisition.content_sha256`
    （取得したGeoTIFFの内容ハッシュ）である。`acquisition`はnullable（既存データ・
    直接生成されたテストデータとの後方互換のため）だが、設定されている場合は
    `on_delete=PROTECT`とし、来歴が参照中の取得記録が無言で消えないようにしている。
    """

    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="displacement_velocities"
    )
    fiscal_year = models.CharField(max_length=8)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    velocity_cm_per_year = models.FloatField()
    source = models.CharField(max_length=64, default="gsi_sar_tsa")
    acquisition = models.ForeignKey(
        DisplacementAcquisition,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="velocities",
    )

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
