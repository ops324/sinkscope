"""Triage（意思決定支援層）のモデル。

SinkScope は1プロダクト・2モジュール構成（docs/SPEC.md §1）:
  - Monitor（backend/analysis/）: 100%実データ。ここには一切の合成データを含めない。
  - Triage（本アプリ）: Monitor の実成果を点検優先度に翻訳する層。疑似管路データは
    このアプリに限定し、`Illustrative` バッジで実データと区別する。

誠実性上の必須事項（独立敵対的監査の指摘を反映。docs/SPEC.md §7・triage/scoring.py
のモジュールdocstring参照）:
  - 本AOI・本データでのパーミュテーション検定（analysis/permutation.py）は、
    直近の実測（docs/SPEC.md §7.3）では「陥没箇所は変位速度がより負に偏る」
    という仮説を支持しなかった。この検定はMonitorの再構築（build_monitor）で
    再実行され得るため、具体的なp値はここに固定で書かない
    （analysis.permutation.summarize_result()が常に最新値から要約する）。
    したがってここで算出する優先度は「検証済み予測」ではない。
  - `Illustrative` バッジは疑似パイプという「データ」だけでなく、優先度算出という
    「手法」自体が未検証であることも免責しなければならない。バッジを剥がすような
    エクスポート（PDF/CSV等）は提供しない。
  - MeshPriority.priority_index は内部計算値であり、APIでは連続スコアとして
    公開しない。必ず順序尺度のtierに離散化してから公開する（scoring.py参照）。
"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from core.models import MeshCell, STORAGE_SRID

# 本モジュール全体を通じて、優先度算出手法は本プロジェクト自身の統計検定に
# 支持されていない。将来AOI拡大や年度蓄積でnが確保され再検証されるまでFalseのまま
# とする（scoring.pyのMETHOD_VALIDATEDと一致させること）。
METHOD_VALIDATED = False

# 疑似管路の管種は、実在の管路分類体系と誤認されないよう例示的な一般名称に留める
# （架空データであることが一目でわかるようにするための意図的な選択）。
PIPE_MATERIAL_CHOICES = [
    ("illustrative_concrete", "ヒューム管(例示)"),
    ("illustrative_ceramic", "陶管(例示)"),
    ("illustrative_pvc", "塩ビ管(例示)"),
    ("illustrative_steel", "鋼管(例示)"),
]

TIER_CHOICES = [
    ("high", "高"),
    ("medium", "中"),
    ("low", "低"),
]


class SyntheticPipe(models.Model):
    """疑似管路（Illustrative）。

    実際の管路台帳が存在しないため、OSM道路網のセンターラインをそのまま
    仮想パイプの幾何として再利用し、道路網上へ合成配置する
    （README「Triage」節参照）。布設年・管種はseed固定の疑似乱数による架空値で、
    実在の管路台帳の代わりにはならない。フロントは本モデル由来の地物を
    常に `Illustrative` バッジと共にのみ描画すること。
    """

    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="synthetic_pipes"
    )
    geom = gis_models.LineStringField(srid=STORAGE_SRID)
    osm_way_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="配置元のOSM way ID(由来追跡用。架空属性ではない)",
    )
    seed = models.PositiveIntegerField(help_text="決定的生成に使った乱数シード")
    install_year = models.PositiveSmallIntegerField(help_text="架空の布設年(Illustrative)")
    pipe_material = models.CharField(
        max_length=32, choices=PIPE_MATERIAL_CHOICES, help_text="架空の管種(Illustrative)"
    )
    is_synthetic = models.BooleanField(default=True, editable=False)

    class Meta:
        indexes = [models.Index(fields=["mesh_cell"])]

    def __str__(self):
        return f"SyntheticPipe#{self.pk} ({self.mesh_cell.mesh_code}, illustrative)"


class TriageRun(models.Model):
    """generate_triageコマンド1回の実行記録（analysis.AnalysisRunの姉妹モデル）。

    metrics_jsonには最低限、以下を必ず記録する（誠実性フレームワークの一部）:
      - method_validated: 常にFalse（このプロジェクトの検定は仮説を支持していない）
      - method_validation_note: その理由の平文説明
      - pipe_count: 生成した疑似管路数
      - baseline_road_length_spearman_rho: priority_indexと道路長単独ランキングとの
        Spearman順位相関(「結局ただの道路長地図では？」への自己点検。docs/SPEC.md §7.1)
    """

    created_at = models.DateTimeField(auto_now_add=True)
    seed = models.PositiveIntegerField()
    params_json = models.JSONField(default=dict, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"TriageRun#{self.pk} ({self.created_at:%Y-%m-%d %H:%M})"


class MeshPriority(models.Model):
    """メッシュ単位の点検優先度（analysis.MeshSummaryの姉妹モデル）。

    重要: priority_index は内部計算のための連続値であり、「ハザードスコア」でも
    「期待陥没率」でもない。APIでは公開せず、tier（高/中/低の順序尺度）のみを
    公開する。各構成要素(velocity_cm_per_year等)は実測値そのままなので、
    分解表示のためAPIでも公開してよい（Monitorの実データと同一の値）。
    """

    mesh_cell = models.ForeignKey(
        MeshCell, on_delete=models.CASCADE, related_name="triage_priorities"
    )
    run = models.ForeignKey(TriageRun, on_delete=models.CASCADE, related_name="mesh_priorities")

    # 内部計算値。APIでは非公開(scoring.pyのAPI変換関数を必ず経由すること)。
    priority_index = models.FloatField()
    tier = models.CharField(max_length=8, choices=TIER_CHOICES)

    # 構成要素の実測値の分解(Monitorの実データそのもの。公開可)。
    velocity_cm_per_year = models.FloatField(null=True, blank=True)
    road_length_m = models.FloatField(null=True, blank=True)
    sewer_event_count = models.PositiveIntegerField(default=0)
    pipe_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mesh_cell", "run"], name="unique_mesh_priority_per_run"
            )
        ]
        indexes = [models.Index(fields=["run"]), models.Index(fields=["tier"])]
