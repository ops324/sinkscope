"""メッシュ単位の実データを1行に集約し、表示用のMeshSummaryへ永続化する。

ここで作るのは「予測」ではなく、core側の各テーブル（DisplacementVelocity, GroundClass,
RoadExposure, SubsidenceEvent）に既にある実測値の集約に過ぎない。派生的な加工
（回帰・スコアリング・ハザード色付け）は一切行わない（docs/SPEC.md §7参照）。

event_count/sewer_event_count はここでは記述・可視化にのみ用いる。これらを入力として
回帰・分類モデルを学習する処理は本プロジェクトのどこにも存在しない
（groundtruth.pyのモジュールdocstring、permutation.pyの反循環ガード参照）。
"""
from __future__ import annotations

import math

import pandas as pd
from django.db.models import Count, Q

from core.models import DisplacementVelocity, MeshCell

from .groundtruth import SEWER_CAUSE_KEYWORD
from .models import AnalysisRun, MeshSummary


def latest_fiscal_year() -> str | None:
    """取込済みDisplacementVelocityのうち最新の年度を返す（現状は単一年度のみ想定。
    docs/SPEC.md §4.1参照：GSIから得られるのは常に年度スナップショット1枚のみ）。
    """
    years = list(DisplacementVelocity.objects.values_list("fiscal_year", flat=True).distinct())
    return max(years) if years else None


def build_summary_frame(fiscal_year: str | None = None) -> pd.DataFrame:
    """mesh_code昇順で決定的な、メッシュ単位の実データ集約フレームを組む。"""
    fiscal_year = fiscal_year or latest_fiscal_year()

    queryset = (
        MeshCell.objects.all()
        .order_by("mesh_code")
        .annotate(
            event_count=Count("subsidence_events", distinct=True),
            sewer_event_count=Count(
                "subsidence_events",
                filter=Q(subsidence_events__cause_facility__icontains=SEWER_CAUSE_KEYWORD),
                distinct=True,
            ),
        )
        .select_related("ground_class", "road_exposure")
    )

    velocity_by_cell = dict(
        DisplacementVelocity.objects.filter(fiscal_year=fiscal_year).values_list(
            "mesh_cell_id", "velocity_cm_per_year"
        )
    )

    rows = []
    for cell in queryset:
        ground = getattr(cell, "ground_class", None)
        road = getattr(cell, "road_exposure", None)
        rows.append(
            {
                "mesh_cell_id": cell.id,
                "mesh_code": cell.mesh_code,
                "velocity_cm_per_year": velocity_by_cell.get(cell.id),
                "land_use_class": getattr(ground, "land_use_class", "") or "",
                "elevation_m": getattr(ground, "elevation_m", None),
                "road_length_m": getattr(road, "road_length_m", None),
                "event_count": cell.event_count,
                "sewer_event_count": cell.sewer_event_count,
            }
        )

    frame = pd.DataFrame(
        rows,
        columns=[
            "mesh_cell_id",
            "mesh_code",
            "velocity_cm_per_year",
            "land_use_class",
            "elevation_m",
            "road_length_m",
            "event_count",
            "sewer_event_count",
        ],
    )
    frame = frame.sort_values("mesh_code").reset_index(drop=True)
    frame.attrs["fiscal_year"] = fiscal_year
    return frame


def _clean_float(value) -> float | None:
    """pandasの数値列はPythonのNoneをNaNへ暗黙変換する(float64列の仕様)。
    DB/APIへは「データなし」として正しくNULL/nullで届けるため、ここで戻す。
    これを怠るとDjangoのJsonResponseはPythonのjson.dumps(allow_nan=True)既定動作で
    非標準の`NaN`トークンをそのまま出力し、ブラウザのJSON.parseが構文エラーで
    落ちる(実際にこの不具合が発生し、本関数で修正した)。
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


def persist_summary(frame: pd.DataFrame, run: AnalysisRun) -> int:
    """build_summary_frameの結果をMeshSummaryへbulk書き込みする（runごとに新規行）。"""
    objs = [
        MeshSummary(
            mesh_cell_id=int(row.mesh_cell_id),
            run=run,
            velocity_cm_per_year=_clean_float(row.velocity_cm_per_year),
            land_use_class=row.land_use_class,
            elevation_m=_clean_float(row.elevation_m),
            road_length_m=_clean_float(row.road_length_m),
            event_count=int(row.event_count),
            sewer_event_count=int(row.sewer_event_count),
        )
        for row in frame.itertuples()
    ]
    MeshSummary.objects.bulk_create(objs)
    return len(objs)
