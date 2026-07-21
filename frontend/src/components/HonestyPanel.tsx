import { useEffect, useState } from "react";

import { fetchAnalysisRunLatest, type AnalysisRunLatestResponse } from "../api/client";

function formatPValue(p: number): string {
  return p < 0.001 ? "<0.001" : p.toFixed(3);
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
            <span>AOI内 陥没イベント総数</span>
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
              <p className="honesty-hypothesis">仮説: {data.metrics.permutation_test.hypothesis}</p>
              <div className="metric-row">
                <span>片側p値</span>
                <strong>{formatPValue(data.metrics.permutation_test.p_value_one_sided)}</strong>
              </div>
              <div className="metric-row">
                <span>両側p値</span>
                <strong>{formatPValue(data.metrics.permutation_test.p_value_two_sided)}</strong>
              </div>
              <div className="metric-row">
                <span>n（検定対象セル数）</span>
                <strong>
                  {data.metrics.permutation_test.k_sewer_cells}
                  {data.metrics.permutation_test.underpowered ? "（underpowered）" : ""}
                </strong>
              </div>
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
