"""build_monitorコマンドの本体。

順序は常に固定：
  1. AOI内イベントのn実測（groundtruth.count_aoi_events） ― nゲート判定の根拠。
  2. 実データ集約フレームの構築（features.build_summary_frame） ― 予測は行わない。
  3. nゲートを満たす場合のみ、付録の空間パーミュテーション検定（permutation.run_permutation_test）。
  4. 上記すべてをAnalysisRunに記録し、MeshSummaryをbulk書き込み（1回の呼び出しで新規run）。

この順序自体が誠実性フレームワークの一部：nを検定より先に測ることで、
「都合よく検定できる形にデータを選ぶ」逆順を構造的に排除している。
"""
from __future__ import annotations

from django.db import transaction

from .features import build_summary_frame, latest_fiscal_year, persist_summary
from .groundtruth import SEWER_CAUSE_KEYWORD, count_aoi_events, in_aoi_events
from .models import AnalysisRun
from .permutation import N_PERMUTATIONS, RANDOM_SEED, run_permutation_test


def run(fiscal_year: str | None = None, seed: int = RANDOM_SEED) -> AnalysisRun:
    fiscal_year = fiscal_year or latest_fiscal_year()
    event_summary = count_aoi_events()

    frame = build_summary_frame(fiscal_year=fiscal_year)

    if event_summary["permutation_test_eligible"]:
        sewer_cell_ids = {
            event.mesh_cell_id
            for event in in_aoi_events(cause_facility_contains=SEWER_CAUSE_KEYWORD)
        }
        permutation_result = run_permutation_test(
            frame, sewer_cell_ids, n_permutations=N_PERMUTATIONS, seed=seed
        )
    else:
        permutation_result = {
            "skipped": True,
            "reason": (
                f"AOI内下水道原因イベント数({event_summary['in_aoi_sewer_event_count']}) < "
                f"{event_summary['permutation_test_min_n']} のため未実施。"
                "統計検定は行わず、視覚的な重ね合わせと正直なn開示のみ提示する。"
            ),
        }

    with transaction.atomic():
        run_obj = AnalysisRun.objects.create(
            fiscal_year=fiscal_year or "",
            params_json={"seed": seed, "n_permutations": N_PERMUTATIONS},
            metrics_json={**event_summary, "permutation_test": permutation_result},
        )
        persist_summary(frame, run_obj)

    return run_obj
