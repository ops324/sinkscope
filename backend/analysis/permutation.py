"""付録の反証検定：空間パーミュテーション（並べ替え）検定。

問い：「陥没（下水道原因）を含むメッシュセルは、含まないセルより変位速度が負に
偏るか？」

道路曝露のある適格セル（road_length_m > 0）の母集団から、観測された下水道原因
イベントが占めるセル数と同数をランダムに再選択し、観測統計量（陥没セルの平均
velocity − 残りの適格セルの平均velocity）を多数回再計算してnull分布を作る。
観測値をnull分布の中に置いて正確p値を得る、反証可能でリークのない検定。

n < PERMUTATION_TEST_MIN_N（groundtruth.py参照）の場合は build.py がこの検定
自体を呼ばずスキップし、その旨をAnalysisRunへ正直に記録する。

注意（限界の明示）：ここでの「適格セル」は road_length_m > 0 という粗い曝露近似
であり、実際の点検・報告強度（管理者区分ごとの報告完全性の違い等）までは
再現していない。これは「陥没が起きる場所」と「陥没が報告される場所」を区別
できないという、本プロジェクト全体の限界（docs/SPEC.md §5）の一部である。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .groundtruth import PERMUTATION_TEST_MIN_N

N_PERMUTATIONS = 10_000
RANDOM_SEED = 42

LIMITATION_NOTE = (
    "適格セルはroad_length_m>0という粗い曝露近似であり、管理者区分ごとの報告強度の"
    "違い等は再現していない。「陥没が起きる場所」と「陥没が報告される場所」を"
    "区別できない点は本検定でも解消されない。"
)


def eligible_pool(frame: pd.DataFrame) -> pd.DataFrame:
    """道路曝露があり、変位速度が観測されているセルのみを検定対象の母集団とする
    （road_length_m==0のセルは陥没報告の機会が事実上ないため、母集団から除外する）。
    """
    return frame[
        frame["road_length_m"].notna()
        & (frame["road_length_m"] > 0)
        & frame["velocity_cm_per_year"].notna()
    ]


def _mean_diff(sample_mask: np.ndarray, velocity: np.ndarray) -> float:
    return float(velocity[sample_mask].mean() - velocity[~sample_mask].mean())


def run_permutation_test(
    frame: pd.DataFrame,
    sewer_mesh_cell_ids: set[int],
    n_permutations: int = N_PERMUTATIONS,
    seed: int = RANDOM_SEED,
) -> dict:
    """陥没(下水道原因)を含むセルと含まないセルの平均変位速度差を、空間パーミュテー
    ション検定で評価する。

    反循環の保証：この関数は event_count/sewer_event_count を特徴量として回帰に
    使わない。行うのは「観測された位置」と「ランダムな位置」の比較のみであり、
    イベントは検定対象（ターゲット）としてのみ使われる。
    """
    pool = eligible_pool(frame)
    velocity = pool["velocity_cm_per_year"].to_numpy()
    mesh_cell_ids = pool["mesh_cell_id"].to_numpy()

    observed_mask = np.isin(mesh_cell_ids, list(sewer_mesh_cell_ids))
    k = int(observed_mask.sum())

    if k == 0 or k >= len(pool):
        return {
            "skipped": True,
            "reason": (
                "陥没(下水道原因)セルが適格プール内に見つからない、"
                "またはプール全体と一致するため検定不能"
            ),
        }

    observed_stat = _mean_diff(observed_mask, velocity)

    rng = np.random.default_rng(seed)
    n = len(pool)
    null_stats = np.empty(n_permutations)
    for i in range(n_permutations):
        idx = rng.choice(n, size=k, replace=False)
        mask = np.zeros(n, dtype=bool)
        mask[idx] = True
        null_stats[i] = _mean_diff(mask, velocity)

    # 片側検定：「陥没セルの方がより負（沈下側）に偏るか」という有向仮説
    # （docs/SPEC.md §7の確定判断）。両側p値も参考値として併記する。
    p_value_one_sided = float(np.mean(null_stats <= observed_stat))
    p_value_two_sided = float(np.mean(np.abs(null_stats) >= abs(observed_stat)))

    return {
        "skipped": False,
        "hypothesis": "陥没(下水道原因)を含むセルは、含まないセルより変位速度が負に偏る",
        "unit_of_analysis": "mesh_cell（陥没地名の重心が落ちるメッシュセル。字と1:1対応とは限らない）",
        "eligible_pool_size": n,
        "k_sewer_cells": k,
        "observed_mean_diff_cm_per_year": observed_stat,
        "n_permutations": n_permutations,
        "seed": seed,
        "p_value_one_sided": p_value_one_sided,
        "p_value_two_sided": p_value_two_sided,
        "underpowered": k < PERMUTATION_TEST_MIN_N,
        "limitation_note": LIMITATION_NOTE,
    }
