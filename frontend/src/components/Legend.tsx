import { LAND_USE_LABELS, elevationColor, landUseColor, roadLengthColor, velocityColor } from "../map/colors";
import type { LayerKey } from "../map/types";

function rgba([r, g, b, a]: readonly [number, number, number, number]): string {
  return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(2)})`;
}

function GradientBar({
  stops,
  labels,
}: {
  stops: [string, string, string];
  labels: [string, string, string];
}) {
  return (
    <div className="legend-gradient">
      <div className="legend-bar" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} />
      <div className="legend-scale">
        <span>{labels[0]}</span>
        <span>{labels[1]}</span>
        <span>{labels[2]}</span>
      </div>
    </div>
  );
}

export default function Legend({ activeLayer }: { activeLayer: LayerKey }) {
  return (
    <div className="legend">
      <h3>凡例</h3>

      {activeLayer === "velocity" && (
        <>
          <GradientBar
            stops={[rgba(velocityColor(-0.5)), rgba(velocityColor(0)), rgba(velocityColor(0.5))]}
            labels={["-0.5 (隆起側)", "0", "+0.5 (沈下側)"]}
          />
          <p className="legend-caveat">
            実測値をそのまま表示（ハザード判定ではない）。GSI公表精度は概ね±数mm/年で、
            本AOI平均はその精度限界に近いため、セル単位の符号は解釈しないこと。
          </p>
        </>
      )}

      {activeLayer === "elevation" && (
        <GradientBar
          stops={[rgba(elevationColor(-8)), rgba(elevationColor(12)), rgba(elevationColor(32))]}
          labels={["-8 m", "12 m", "32 m"]}
        />
      )}

      {activeLayer === "road_length" && (
        <GradientBar
          stops={[rgba(roadLengthColor(0)), rgba(roadLengthColor(2250)), rgba(roadLengthColor(4500))]}
          labels={["0 m", "2,250 m", "4,500 m"]}
        />
      )}

      {activeLayer === "land_use" && (
        <div className="legend-categorical">
          {Object.entries(LAND_USE_LABELS).map(([code, label]) => (
            <div key={code} className="legend-swatch-row">
              <span className="legend-swatch" style={{ background: rgba(landUseColor(code)) }} />
              <span>{label}</span>
            </div>
          ))}
          <p className="legend-caveat">
            国土数値情報 土地利用細分メッシュ(L03-b)のコード表による。メッシュ内の最頻値。
          </p>
        </div>
      )}

      <div className="legend-events">
        <div className="legend-swatch-row">
          <span className="legend-swatch legend-swatch--dot" style={{ background: "rgba(255, 90, 30, 0.92)" }} />
          <span>陥没事案（下水道原因）</span>
        </div>
        <div className="legend-swatch-row">
          <span className="legend-swatch legend-swatch--dot" style={{ background: "rgba(225, 225, 225, 0.65)" }} />
          <span>陥没事案（その他要因）</span>
        </div>
      </div>
    </div>
  );
}
