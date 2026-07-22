"""透明・多基準の点検優先度ヒューリスティック。

これは「予測」でも「回帰・分類モデル」でもない。Monitorの実測値
(analysis.features.build_summary_frame)を、事前に固定した重みで線形結合し、
1つの順序(tier)に変換するだけの意思決定支援ヒューリスティックである。

誠実性上の必須制約(独立敵対的監査の指摘、docs/SPEC.md §5・§7と合わせて厳守):

  1. 学習・回帰は一切行わない。DEFAULT_WEIGHTSはデータから推定した係数ではなく、
     事前に固定した業務ヒューリスティックの重みである。

  2. 本プロジェクト自身のパーミュテーション検定(analysis/permutation.py)は
     「陥没(下水道原因)を含むセルは、含まないセルより変位速度が負に偏る」という
     仮説を支持しなかった(片側p=0.962、両側p=0.122。docs/SPEC.md §7.3)。
     したがって沈下シグナル項(subsidence_signal)は検証済みの予測子ではなく、
     あくまで「一般的に地盤変位は点検対象を選ぶ際の考慮要素になり得る」という
     事前の業務知識に基づく重み付けに過ぎない。METHOD_VALIDATED=Falseとして
     常に明示する。

  3. 連続値priority_indexをAPIで生の「スコア」として公開しない。必ずassign_tiers()
     で順序尺度のtier(high/medium/low、分位ベース)に離散化してから公開する
     (独立敵対的監査 guardrail (b))。

  4. road_length単独ランキングとのSpearman順位相関を必ず算出・開示する
     ("結局ただの道路長地図では?"という自己点検。docs/SPEC.md §7.1で却下された
     per-cell連続choroplethと同じ誤りに陥っていないかの検証)。

  5. event_count/sewer_event_countは特徴量として"学習"されない
     (単純な固定重みの一項目として扱われるのみで、係数を推定するようなことは
     しない)。analysis/permutation.pyの反循環ガードと同じ精神を維持する。
"""
from __future__ import annotations

import pandas as pd

# 検定は「陥没箇所は変位速度がより負に偏る」仮説を支持しなかった(片側p=0.962)。
# 将来AOI拡大や年度蓄積でnが確保され再検証されるまでFalseのまま
# (triage.models.METHOD_VALIDATEDと一致させること)。
METHOD_VALIDATED = False
METHOD_VALIDATION_NOTE = (
    "本ランキングの手法は未検証である。本プロジェクト自身の空間パーミュテーション"
    "検定は「陥没(下水道原因)箇所は変位速度がより負に偏る」という仮説を支持しなかった"
    "(片側p=0.962、両側p=0.122、docs/SPEC.md §7.3)。したがって沈下シグナル項の重みは"
    "検証済みの予測係数ではなく、事前の業務ヒューリスティックに過ぎない。本ランキングは"
    "点検ワークリストがどう見え・どう振る舞うかのUI実証であり、この地域が実際に"
    "高優先度であることを統計的に示すものではない。"
)

DEFAULT_WEIGHTS = {
    "subsidence_signal": 0.4,  # |min(velocity_cm_per_year, 0)| (沈下方向のみ)
    "road_exposure": 0.3,  # road_length_m (点検対象量としての曝露)
    "past_events": 0.3,  # sewer_event_count (運用上の再訪ヒューリスティック)
}

TIER_LABELS = ["low", "medium", "high"]


def eligible_pool(frame: pd.DataFrame) -> pd.DataFrame:
    """優先度算出の母集団: 道路曝露があるメッシュのみ(道路が無ければ点検対象がない)。

    analysis.permutation.eligible_poolと同じ考え方(road_length_m>0)を再利用する。
    """
    return frame[frame["road_length_m"].notna() & (frame["road_length_m"] > 0)].copy()


def _normalize(series: pd.Series) -> pd.Series:
    """min-max正規化。全て同値(レンジ0)の場合は0を返す(ゼロ割回避)。"""
    lo, hi = series.min(), series.max()
    if hi - lo == 0:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


def compute_priority_index(
    frame: pd.DataFrame, weights: dict[str, float] | None = None
) -> pd.DataFrame:
    """適格プールに対し、事前固定の重み付き線形結合でpriority_indexを算出する。

    回帰・分類モデルの学習は行わない(重みは引数として外から与えられる定数)。
    戻り値のフレームにはpriority_indexおよび構成要素の正規化前の実測値も残す
    (分解表示のため)。
    """
    weights = weights or DEFAULT_WEIGHTS
    pool = eligible_pool(frame)

    subsidence_signal = pool["velocity_cm_per_year"].fillna(0).clip(upper=0).abs()
    road_exposure = pool["road_length_m"].fillna(0)
    past_events = pool["sewer_event_count"].fillna(0)

    pool["priority_index"] = (
        weights["subsidence_signal"] * _normalize(subsidence_signal)
        + weights["road_exposure"] * _normalize(road_exposure)
        + weights["past_events"] * _normalize(past_events)
    )
    return pool


def assign_tiers(frame: pd.DataFrame, n_tiers: int = 3) -> pd.DataFrame:
    """priority_indexを分位ベースでtier(low/medium/high)に離散化する。

    独立敵対的監査 guardrail (b): 連続スコアをAPIに出さないための必須ステップ。
    同順位が多く分位が縮退する場合はrank(method="first")でタイブレークする。
    """
    if len(frame) == 0:
        frame["tier"] = pd.Series(dtype="object")
        return frame

    ranks = frame["priority_index"].rank(method="first")
    quantile_bin = pd.qcut(ranks, q=n_tiers, labels=TIER_LABELS[:n_tiers])
    frame = frame.copy()
    frame["tier"] = quantile_bin.astype(str)
    return frame


def baseline_correlation(frame: pd.DataFrame) -> float | None:
    """priority_indexとroad_length_m単独ランキングとのSpearman順位相関。

    docs/SPEC.md §7.1: per-cell連続choroplethは「実質『道路長の地図』を
    ハザード色で偽装するだけになりかねない」として却下されている。本関数は
    そのリスクが実際にどの程度あるかを、tier化する前の連続値で自己点検する
    (相関が高いほど、優先度が単なる道路長の言い換えに近いという注意信号)。
    """
    if len(frame) < 2:
        return None
    corr = frame["priority_index"].corr(frame["road_length_m"], method="spearman")
    return None if pd.isna(corr) else float(corr)
