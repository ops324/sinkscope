"""generate_triageコマンドの本体(analysis/build.pyの姉妹モジュール)。

順序:
  1. 疑似管路の準備(未生成、または --regenerate-pipes 指定時のみ生成。Overpass API
     への再アクセスを避けるための冪等性)。
  2. Monitorの実データ集約フレーム(analysis.features.build_summary_frame)を取得し、
     メッシュごとの疑似管路数を結合する。
  3. 優先度ヒューリスティックを適用してtierを算出する(回帰・分類モデルの学習は
     一切行わない。triage/scoring.py参照)。
  4. road_length単独ベースラインとのSpearman順位相関を算出する。
  5. 最新AnalysisRunのMonitor検定結果からmethod_validation_noteをその場で組み立て
     (ハードコードされたp値の陳腐化を防ぐ。analysis.permutation.summarize_result参照)、
     重み・パイプ数・相関・method_validated=Falseと併せてTriageRunに記録し、
     MeshPriorityをbulk書き込みする(1回の呼び出しで新規run)。
"""
from __future__ import annotations

import math

from django.db import transaction

from analysis.features import build_summary_frame
from analysis.models import AnalysisRun
from analysis.permutation import summarize_result as summarize_permutation_result

from .models import MeshPriority, SyntheticPipe, TriageRun
from .pipes import generate_synthetic_pipes
from .scoring import (
    DEFAULT_WEIGHTS,
    METHOD_VALIDATED,
    assign_tiers,
    baseline_correlation,
    compute_priority_index,
    method_validation_note,
)


def _clean_float(value) -> float | None:
    """analysis/features.pyの同名関数と同じ理由: pandasのNaNをJSON安全なNoneへ戻す。"""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


def _pipe_counts_by_mesh() -> dict[int, int]:
    counts = SyntheticPipe.objects.values_list("mesh_cell_id").order_by()
    tally: dict[int, int] = {}
    for (mesh_cell_id,) in counts:
        tally[mesh_cell_id] = tally.get(mesh_cell_id, 0) + 1
    return tally


def run(
    seed: int = 42,
    weights: dict[str, float] | None = None,
    regenerate_pipes: bool = False,
) -> TriageRun:
    weights = weights or DEFAULT_WEIGHTS

    if regenerate_pipes or not SyntheticPipe.objects.exists():
        pipe_count = generate_synthetic_pipes(seed=seed)
    else:
        pipe_count = SyntheticPipe.objects.count()

    frame = build_summary_frame()
    pipe_counts = _pipe_counts_by_mesh()
    frame["pipe_count"] = frame["mesh_cell_id"].map(pipe_counts).fillna(0).astype(int)

    scored = compute_priority_index(frame, weights=weights)
    scored = assign_tiers(scored)
    correlation = baseline_correlation(scored)

    latest_analysis_run = AnalysisRun.objects.order_by("-created_at").first()
    permutation_sentence = summarize_permutation_result(
        latest_analysis_run.metrics_json if latest_analysis_run else {}
    )

    with transaction.atomic():
        run_obj = TriageRun.objects.create(
            seed=seed,
            params_json={"weights": weights},
            metrics_json={
                "method_validated": METHOD_VALIDATED,
                "method_validation_note": method_validation_note(permutation_sentence),
                "pipe_count": pipe_count,
                "eligible_mesh_count": len(scored),
                "baseline_road_length_spearman_rho": correlation,
            },
        )

        objs = [
            MeshPriority(
                mesh_cell_id=int(row.mesh_cell_id),
                run=run_obj,
                priority_index=float(row.priority_index),
                tier=row.tier,
                velocity_cm_per_year=_clean_float(row.velocity_cm_per_year),
                road_length_m=_clean_float(row.road_length_m),
                sewer_event_count=int(row.sewer_event_count),
                pipe_count=int(row.pipe_count),
            )
            for row in scored.itertuples()
        ]
        MeshPriority.objects.bulk_create(objs)

    return run_obj
