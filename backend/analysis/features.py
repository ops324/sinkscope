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

from core.models import DisplacementAcquisition, DisplacementVelocity, MeshCell

from .groundtruth import SEWER_CAUSE_KEYWORD
from .models import AnalysisRun, MeshSummary


def latest_fiscal_year() -> str | None:
    """表示・集計に使う変位速度の年度を1つ返す（現状は単一年度のみ想定。
    docs/SPEC.md §4.1参照：GSIから得られるのは常に年度スナップショット1枚のみ）。

    `fiscal_year`はDisplacementAcquisitionのbest-effortラベルに過ぎず、真のヴィンテージ
    識別子はcontent_sha256である。取得時刻からの未検証推定
    （`fiscal_year_provenance="unverified_retrieval_time"`）は、GSIの成果公開ラグにより
    実際の成果年度より新しい値になりがちなため、**年度文字列の大小では選ばない**。
    大小で選ぶと、未検証の推定年度が「数字が大きいから」という理由だけで
    filename/operator_override由来の検証済み年度を追い越してしまう
    （来歴汚染バグF9の再発パターンそのもの）。

    優先順位:
      1. `fiscal_year_provenance`が検証済み（"filename"/"operator_override"）な
         DisplacementAcquisitionのうち、`retrieved_at`が最新のもの。
      2. 検証済みが1件も無ければ、`retrieved_at`が最新のDisplacementAcquisition
         （未検証だが、他に選びようがないため採用する）。
      3. DisplacementAcquisitionが1件も無い場合（`acquisition`未設定の旧データ・
         テストで`DisplacementVelocity`を直接生成したケース）のみ、従来どおり
         `DisplacementVelocity.fiscal_year`のdistinct maxにフォールバックする。
    """
    verified = (
        DisplacementAcquisition.objects.filter(
            fiscal_year_provenance__in=["filename", "operator_override"]
        )
        .order_by("-retrieved_at")
        .first()
    )
    if verified is not None:
        return verified.fiscal_year

    any_acquisition = DisplacementAcquisition.objects.order_by("-retrieved_at").first()
    if any_acquisition is not None:
        return any_acquisition.fiscal_year

    years = list(DisplacementVelocity.objects.values_list("fiscal_year", flat=True).distinct())
    return max(years) if years else None


def displacement_provenance(frame: pd.DataFrame) -> dict:
    """build_summary_frameが実際に集約した変位速度データの来歴を返す。

    「fiscal_yearから最新1件のDisplacementAcquisitionを後付けで引く」のではなく、
    このframeに含まれる各メッシュの`DisplacementVelocity`行が実際に指す
    `acquisition_id`を集計する。これにより、`AnalysisRun.metrics_json`に記録される
    来歴が「このAnalysisRunを実際に生んだラスタ」と食い違わないことを保証する
    （fiscal_year単位で後から引き直すと、同一年度に複数回の取込・部分更新があった
    場合に実際使われたラスタと異なるacquisitionを来歴として記録しかねない）。

    acquisitionが1件も紐付いていない（旧データ）場合は`acquisitions`が空リストになる。
    複数のacquisitionが混在する場合はその全件を返す（呼び出し側で件数を見れば
    「単一ラスタ由来」か「混在」かが分かる）。
    """
    fiscal_year = frame.attrs.get("fiscal_year")
    mesh_cell_ids = [int(v) for v in frame["mesh_cell_id"] if pd.notna(v)]
    if not mesh_cell_ids or fiscal_year is None:
        return {"fiscal_year": fiscal_year, "acquisitions": []}

    acquisition_ids = list(
        DisplacementVelocity.objects.filter(
            mesh_cell_id__in=mesh_cell_ids,
            fiscal_year=fiscal_year,
            acquisition__isnull=False,
        )
        .values_list("acquisition_id", flat=True)
        .distinct()
    )
    acquisitions = [
        {
            "content_sha256": acq.content_sha256,
            "retrieved_at": acq.retrieved_at.isoformat(),
            "fiscal_year": acq.fiscal_year,
            "fiscal_year_provenance": acq.fiscal_year_provenance,
            "api_file_name": acq.api_file_name,
        }
        for acq in DisplacementAcquisition.objects.filter(id__in=acquisition_ids)
    ]
    return {"fiscal_year": fiscal_year, "acquisitions": acquisitions}


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
