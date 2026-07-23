import type { MeshFeatureProperties } from "../api/client";
import { landUseLabel } from "../map/colors";

// Monitor選択コックピットの詳細パネル(D3)。
//
// 純粋な表示コンポーネント: データ取得はせず、App が lift した選択メッシュの実測値を
// 落ち着いて読める常設の場として描画する。表示項目は既存の hover ツールチップ
// (map/MonitorMap.tsx の meshTooltipText)と同一 ―― 予測・スコア・順位は一切足さない。
//
// 誠実性: 過去陥没はメッシュ属性の件数(event_count/sewer_event_count)をそのまま使い、
// 空間結合で新たな主張を作らない。空状態は「未選択」であって「安全」ではない。

function formatVelocity(value: number | null): string {
  return value === null ? "データなし" : `${value.toFixed(3)} cm/年`;
}

function formatElevation(value: number | null): string {
  return value === null ? "データなし" : `${value.toFixed(2)} m`;
}

function formatRoadLength(value: number | null): string {
  return value === null ? "データなし" : `${Math.round(value)} m`;
}

export default function MeshDetailPanel({
  selected,
  loading,
  onClear,
}: {
  selected: MeshFeatureProperties | null;
  loading: boolean;
  onClear: () => void;
}) {
  return (
    <section className="mesh-detail-panel" role="region" aria-label="選択メッシュの詳細">
      <div className="mesh-detail-header">
        <span className="mesh-detail-chip">選択中のメッシュ</span>
        {selected && (
          <button
            type="button"
            className="mesh-detail-clear"
            onClick={onClear}
            aria-label="選択を解除"
          >
            ✕ 解除
          </button>
        )}
      </div>

      {loading && !selected ? (
        <p className="mesh-detail-placeholder">読み込み中…</p>
      ) : selected ? (
        <>
          <div className="metric-row">
            <span>メッシュコード</span>
            <strong>{selected.mesh_code}</strong>
          </div>
          <div className="metric-row">
            <span>変位速度（実測）</span>
            <strong>{formatVelocity(selected.velocity_cm_per_year)}</strong>
          </div>
          <div className="metric-row">
            <span>土地利用</span>
            <strong>{landUseLabel(selected.land_use_class)}</strong>
          </div>
          <div className="metric-row">
            <span>標高</span>
            <strong>{formatElevation(selected.elevation_m)}</strong>
          </div>
          <div className="metric-row">
            <span>道路延長</span>
            <strong>{formatRoadLength(selected.road_length_m)}</strong>
          </div>
          <div className="metric-row">
            <span>過去の陥没報告</span>
            <strong>
              {selected.event_count}件（うち下水道原因 {selected.sewer_event_count}件）
            </strong>
          </div>
          <p className="mesh-detail-disclaimer">
            これは<strong>状況把握</strong>であり、陥没予測ではありません。表示はすべて公開
            データの実測値です。
          </p>
        </>
      ) : (
        <p className="mesh-detail-empty">
          地図のセルをクリックすると実測値を表示します。
          <br />
          <span className="mesh-detail-empty-note">
            未選択は&quot;安全&quot;を意味しません。
          </span>
        </p>
      )}
    </section>
  );
}
