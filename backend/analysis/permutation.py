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

付記（空間自己相関への対応方針）：上記の一様シャッフルnullは各適格セルを交換可能
（i.i.d.）とみなすが、InSAR変位速度は空間的に滑らか（隣接セル間で似た値を取る）で
あり、この前提は厳密には成り立たない。独立敵対的監査の結論に基づき、本検定は
一様null自体は変更せず、代わりに(1)自己相関の強さを示すMoran's I診断
（morans_i_velocity）を付録として開示し、(2)一様p値は「自己相関を無視した
反保守的な下限値（真のp値はこれ以上）」であることを結果に明記する。空間構造を
保存した独自の補正null（トーラス並進等）は採用しない：本AOIのように小さく穴の
多い母集団では、そうした補正が有効配置を内部の密な領域に偏らせ、null分散を
かえって狭めるという未定量のバイアスを持ち込みうるため（設計と却下理由の詳細は
docs/SPEC.md §7参照）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.mesh import mesh_indices_from_code

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


def _lattice_coords(pool: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """適格プールの各セルについて、mesh_codeから格子インデックス(ix, iy)を復元する。

    本AOIではix・iyとも負の値を取る（core.mesh.mesh_indices_from_codeのdocstring参照）。
    """
    codes = pool["mesh_code"].to_numpy()
    ix = np.empty(len(codes), dtype=np.int64)
    iy = np.empty(len(codes), dtype=np.int64)
    for i, code in enumerate(codes):
        ix[i], iy[i] = mesh_indices_from_code(code)
    return ix, iy


def morans_i_velocity(pool: pd.DataFrame) -> float | None:
    """適格プールの変位速度に対する大域Moran's I（ルーク隣接：|Δix|+|Δiy|==1）。

    純粋に記述的な自己相関診断であり、有意性判定やnullの補正には使わない
    （独立敵対的監査の結論：小規模で穴の多い本AOIでは、Iに有意性を付与したり
    これを用いてnullを補正したりすると、未定量のバイアスを持ち込みかねないため）。
    自己相関がなければ期待値は-1/(n-1)。Iがこれより十分大きければ正の自己相関が
    あり、本検定が用いる一様シャッフルnull（交換可能性を仮定）が過小分散である
    ＝一様p値が反保守的な下限値に過ぎないことの裏付けとなる。

    隣接ペアが存在しない、または速度の分散がゼロの場合はNoneを返す。
    """
    velocity = pool["velocity_cm_per_year"].to_numpy(dtype=float)
    n = len(velocity)
    if n < 2:
        return None

    z = velocity - velocity.mean()
    denom = float((z * z).sum())
    if denom == 0.0:
        return None

    ix, iy = _lattice_coords(pool)
    index = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(ix, iy))}

    numerator = 0.0
    s0 = 0
    for i, (a, b) in enumerate(zip(ix, iy)):
        for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            j = index.get((int(a) + da, int(b) + db))
            if j is not None:
                numerator += z[i] * z[j]
                s0 += 1

    if s0 == 0:
        return None
    return float((n / s0) * (numerator / denom))


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

    morans_i = morans_i_velocity(pool)
    morans_i_expected = -1.0 / (n - 1) if n > 1 else None

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
        "morans_i": morans_i,
        "morans_i_expected": morans_i_expected,
        "p_value_interpretation": _p_value_interpretation(observed_stat, morans_i, morans_i_expected),
    }


def _p_value_interpretation(
    observed_stat: float, morans_i: float | None, morans_i_expected: float | None
) -> str:
    """一様シャッフルp値を「下限値」として解釈するための平易な注記文を組み立てる。

    独立敵対的監査の結論に基づき、空間構造を保存した独自の補正null（トーラス並進等）は
    採用せず、一様p値をそのまま結果とした上で、その限界を正直に開示する方針を取る
    （このモジュールのdocstring「付記」参照）。
    """
    base = (
        "この片側p値は、隣接セル間で変位速度が似た値を取る空間自己相関を無視した"
        "一様シャッフルによるものである。自己相関があると独立な標本数を実際より"
        "多く見積もってしまうため、このp値は反保守的な下限値に過ぎず、真のp値は"
        "これ以上と考えられる。"
    )
    if morans_i is not None and morans_i_expected is not None and morans_i > morans_i_expected:
        base += (
            f"実際にMoran's I（{morans_i:.3f}）は自己相関なしの期待値"
            f"（{morans_i_expected:.3f}）を上回っており、この懸念は裏付けられている。"
        )

    if observed_stat < 0:
        base += "観測差は仮説の方向（陥没セルがより沈下側）と一致している。"
    else:
        base += (
            "観測差は仮説の方向とは逆（陥没セルはむしろ隆起側）であり、"
            "空間自己相関を考慮したとしても結論（仮説不支持）は変わらない。"
        )
    return base


def summarize_result(metrics_json: dict | None) -> str:
    """AnalysisRun.metrics_json(run_permutation_testの結果を含む)から、この検定の
    現状を要約する一文をその場で組み立てる。

    Triage(triage/scoring.py・triage/build.py)とAPI(api/views.py)の双方が、この
    関数を単一の情報源として参照する。以前は両者がそれぞれ独立に「片側p=0.962」を
    ハードコードしており、Monitor側の検定がAOI拡大や年度蓄積で再実行され結果が
    変わっても、Triage側の文言だけ古いまま取り残される恐れがあった
    (独立敵対的監査の指摘)。ここで一箇所に集約することで、参照している側は必ず
    最新の検定結果に追随する。
    """
    permutation = (metrics_json or {}).get("permutation_test") or {}
    if not permutation or permutation.get("skipped"):
        return (
            "本プロジェクト自身の空間パーミュテーション検定はまだ実施されていません"
            "(イベント数nが不足、またはMonitorデータ未取込。analysis/run/latest参照)。"
        )
    p_value = permutation.get("p_value_one_sided")
    if not isinstance(p_value, (int, float)):
        return "本プロジェクト自身の空間パーミュテーション検定の結果を取得できません。"
    verdict = "支持しました" if p_value < 0.05 else "支持しませんでした"
    return (
        "本プロジェクト自身の空間パーミュテーション検定は「陥没(下水道原因)箇所は"
        f"変位速度がより負に偏る」という仮説を{verdict}(片側p={p_value:.3f}、"
        "analysis/run/latest参照)。"
    )
