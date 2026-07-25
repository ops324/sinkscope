from django.db import models

from core.models import MeshCell


class MeshSummary(models.Model):
    """メッシュ単位の実データを表示用に1行へ非正規化したビューテーブル。

    重要: これは「ハザードスコア」でも「期待陥没率」でもない。core側の各テーブル
    （DisplacementVelocity, GroundClass, RoadExposure, SubsidenceEvent）に既にある
    実測値をそのままメッシュ単位で集約し、APIレスポンスを高速化するために持つだけの
    キャッシュである。予測・推論による加工値はここに置かない（PR3のスコープ判断は
    docs/SPEC.md §7参照）。
    """

    # 実行(run)ごとに全メッシュ分の行を新規作成するため、mesh_cellは同一runの中では
    # 一意（下記UniqueConstraint）だが、run間では繰り返し使われる。OneToOneFieldにすると
    # 2回目以降のbuild_monitor実行で衝突するため、通常のForeignKeyにしてある。
    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="analysis_summaries"
    )
    run = models.ForeignKey(
        "AnalysisRun", on_delete=models.CASCADE, related_name="mesh_summaries"
    )
    velocity_cm_per_year = models.FloatField(null=True, blank=True)
    land_use_class = models.CharField(max_length=64, blank=True)
    elevation_m = models.FloatField(null=True, blank=True)
    road_length_m = models.FloatField(null=True, blank=True)
    event_count = models.PositiveIntegerField(default=0)
    sewer_event_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mesh_cell", "run"], name="unique_mesh_summary_per_run"
            )
        ]
        indexes = [models.Index(fields=["run"])]


class AnalysisRun(models.Model):
    """build_monitorコマンド1回の実行記録。再現性・監査証跡のために全メトリクスを残す。

    metrics_jsonには最低限、以下を必ず記録する（誠実性フレームワークの一部。
    docs/SPEC.md §5参照）:
      - in_aoi_event_count: AOI内の陥没イベント総数（実測。SPEC§4.5の「933件」は
        東京都+埼玉県全体の数字であり、AOI内はこれとは別に数える）
      - in_aoi_sewer_event_count: うち下水道原因の件数
      - occupied_oaza_count: イベントが占める字（＝ジオコード重心座標）の数
      - permutation_test: 実施した場合はその結果一式。n不足で未実施の場合は
        {"skipped": true, "reason": "..."}
    """

    created_at = models.DateTimeField(auto_now_add=True)
    fiscal_year = models.CharField(max_length=8, blank=True)
    params_json = models.JSONField(default=dict, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AnalysisRun#{self.pk} ({self.created_at:%Y-%m-%d %H:%M})"
