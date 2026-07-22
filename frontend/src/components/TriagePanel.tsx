import { useEffect, useState } from "react";

import { fetchTriageRanking, type TriageRankingResponse } from "../api/client";
import { TIER_LABELS } from "../map/colors";

function formatRho(rho: number | null): string {
  if (rho === null) return "算出不可";
  return rho.toFixed(3);
}

function velocityText(value: number | null): string {
  return value === null ? "データなし" : `${value.toFixed(3)} cm/年`;
}

function roadLengthText(value: number | null): string {
  return value === null ? "データなし" : `${Math.round(value)} m`;
}

export default function TriagePanel() {
  const [data, setData] = useState<TriageRankingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTriageRanking()
      .then(setData)
      .catch((err: unknown) => setError(String(err)));
  }, []);

  return (
    <aside className="honesty-panel triage-panel">
      <h2>
        Triage について <span className="illustrative-badge">Illustrative</span>
      </h2>
      <p className="honesty-tagline honesty-tagline--warning">
        疑似管路データおよび点検優先度ランキングの<strong>手法自体が未検証</strong>です。
        本プロジェクト自身の統計検定は、この優先度が前提とするハザード関連を
        支持しませんでした。これは検証済み予測ではなく、点検ワークリストが
        どう見え・どう振る舞うかのUI実証です。
      </p>

      {error && <p className="honesty-error">ランキングの取得に失敗しました。</p>}

      {data && !data.exists && (
        <p className="honesty-caveat">
          TriageRunがまだ生成されていません（<code>generate_triage</code>コマンドを実行してください）。
        </p>
      )}

      {data?.exists && (
        <div className="honesty-metrics">
          <div className="metric-row">
            <span>疑似管路数（Illustrative）</span>
            <strong>{data.metrics.pipe_count.toLocaleString()}本</strong>
          </div>
          <div className="metric-row">
            <span>優先度算出対象メッシュ数</span>
            <strong>{data.metrics.eligible_mesh_count.toLocaleString()}</strong>
          </div>

          <div className="permutation-result permutation-result--skipped">
            <p className="permutation-title">自己点検：道路長ベースラインとの順位相関</p>
            <div className="metric-row">
              <span>Spearman順位相関 ρ</span>
              <strong>{formatRho(data.metrics.baseline_road_length_spearman_rho)}</strong>
            </div>
            <p className="honesty-caveat">
              ρが1に近いほど、本ランキングは「道路長だけのランキング」に近いことを意味する
              （docs/SPEC.md §7.1「実質『道路長の地図』をハザード色で偽装するだけになりかねない」
              という懸念への自己点検）。
            </p>
          </div>

          <p className="honesty-caveat">{data.metrics.method_validation_note}</p>

          <h3 className="triage-ranking-title">点検候補メッシュ（tier順）</h3>
          <ol className="triage-ranking-list">
            {data.ranking.slice(0, 15).map((row) => (
              <li key={row.mesh_code} className={`triage-ranking-row triage-ranking-row--${row.tier}`}>
                <div className="triage-ranking-row-header">
                  <span className="triage-tier-badge">{TIER_LABELS[row.tier] ?? row.tier}</span>
                  <span className="triage-mesh-code">{row.mesh_code}</span>
                </div>
                <div className="triage-ranking-breakdown">
                  <span>変位速度(実測): {velocityText(row.velocity_cm_per_year)}</span>
                  <span>道路延長: {roadLengthText(row.road_length_m)}</span>
                  <span>過去の陥没報告(下水道原因): {row.sewer_event_count}件</span>
                  <span>疑似管路数: {row.pipe_count}本</span>
                </div>
              </li>
            ))}
          </ol>
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
