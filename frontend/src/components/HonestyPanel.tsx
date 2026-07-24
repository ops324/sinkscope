import { useEffect, useState } from "react";

import { fetchAnalysisRunLatest, type AnalysisRunLatestResponse } from "../api/client";
import Term from "./Term";

// 初見向けの平易な補足(値そのものは変えない)。
const AOI_HINT =
  "この地図が対象にしている範囲。デモでは江東区・江戸川区・八潮市周辺。AOI＝Area of Interest（対象エリア）。";
const PVALUE_HINT =
  "「もし本当は関係が無くても、偶然だけでこれくらいの差が出る確率」の目安（0〜1）。小さいほど“偶然では説明しにくい”。目安として0.05未満だと「偶然とは考えにくい」とされることが多い。";

function formatPValue(p: number): string {
  return p < 0.001 ? "<0.001" : p.toFixed(3);
}

function formatMoransI(value: number | null): string {
  return value === null ? "算出不能" : value.toFixed(3);
}

export default function HonestyPanel() {
  const [data, setData] = useState<AnalysisRunLatestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAnalysisRunLatest()
      .then(setData)
      .catch((err: unknown) => setError(String(err)));
  }, []);

  return (
    <aside className="honesty-panel">
      <h2>Monitor について</h2>
      <p className="honesty-tagline">
        これは予測ではなく、実データの統合と、実陥没に対する視覚的・(可能な場合は)統計的な答え合わせです。
      </p>

      {error && <p className="honesty-error">メトリクスの取得に失敗しました。</p>}

      {data?.exists && (
        <div className="honesty-metrics">
          <div className="metric-row">
            <span>
              <Term hint={AOI_HINT}>対象エリア</Term>内の陥没イベント総数
            </span>
            <strong>{data.metrics.in_aoi_event_count}件</strong>
          </div>
          <div className="metric-row">
            <span>うち下水道原因</span>
            <strong>{data.metrics.in_aoi_sewer_event_count}件</strong>
          </div>

          {data.metrics.permutation_test.skipped ? (
            <div className="permutation-result permutation-result--skipped">
              <p className="permutation-title">付録：空間パーミュテーション検定 ― 未実施</p>
              <p className="honesty-caveat">{data.metrics.permutation_test.reason}</p>
            </div>
          ) : (
            <div className="permutation-result">
              <p className="permutation-title">付録：空間パーミュテーション検定</p>
              <p className="honesty-plain">
                「下水道が原因の陥没が多い場所ほど、地盤が沈んでいるか？」を統計的に確かめた
                付録です。下の<Term hint={PVALUE_HINT}>p値</Term>が小さいほど、その関係が
                “偶然では説明しにくい”ことを意味します。
              </p>
              <p className="honesty-hypothesis">仮説: {data.metrics.permutation_test.hypothesis}</p>
              <div className="metric-row">
                <span>
                  片側<Term hint={PVALUE_HINT}>p値</Term>（自己相関を無視した下限値）
                </span>
                <strong>{formatPValue(data.metrics.permutation_test.p_value_one_sided)}</strong>
              </div>
              <div className="metric-row">
                <span>
                  両側<Term hint={PVALUE_HINT}>p値</Term>（参考）
                </span>
                <strong>{formatPValue(data.metrics.permutation_test.p_value_two_sided)}</strong>
              </div>
              <div className="metric-row">
                <span>n（検定対象セル数）</span>
                <strong>
                  {data.metrics.permutation_test.k_sewer_cells}
                  {data.metrics.permutation_test.underpowered ? "（underpowered）" : ""}
                </strong>
              </div>
              <div className="metric-row">
                <span>空間自己相関診断（Moran&apos;s I）</span>
                <strong>
                  {formatMoransI(data.metrics.permutation_test.morans_i)}
                  {data.metrics.permutation_test.morans_i_expected !== null
                    ? `（無相関の期待値 ${data.metrics.permutation_test.morans_i_expected.toFixed(3)}）`
                    : ""}
                </strong>
              </div>
              <p className="honesty-caveat">{data.metrics.permutation_test.p_value_interpretation}</p>
              <p className="honesty-caveat">{data.metrics.permutation_test.limitation_note}</p>
            </div>
          )}
        </div>
      )}

      <ul className="honesty-disclaimers">
        {(data?.disclaimers ?? []).map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </aside>
  );
}
