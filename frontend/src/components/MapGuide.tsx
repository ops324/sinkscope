import { useState } from "react";

// 初見の読み手向けの「この地図の見方」。日常語で"何のツールか・どう使うか"を示す。
// 誠実性フレーミング(予測ではなく状況把握)を先頭に置き、詳細な統計は下段の
// HonestyPanelに委ねる。読み終えたら畳める(既定は開いた状態)。
export default function MapGuide() {
  const [open, setOpen] = useState(true);

  return (
    <section className="map-guide" aria-label="この地図の見方">
      <button
        type="button"
        className="map-guide-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>この地図の見方</span>
        <span className="map-guide-caret" aria-hidden="true">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="map-guide-body">
          <p>
            無償の衛星データ（InSAR）で見た<strong>地盤の上下の動き</strong>を、
            <strong>過去の道路陥没</strong>と重ねて眺めるための地図です。
            将来の陥没を予測するものではなく、
            <strong>&quot;気になる場所&quot;を人が見つける</strong>ための状況把握を助けます。
          </p>
          <ol className="map-guide-steps">
            <li>地図の区画をクリック → その場所の実測値が右に出ます。</li>
            <li>左上のボタンで、表示する指標（変位速度・標高など）を切り替えられます。</li>
            <li>オレンジ／灰色の点は、過去に報告された道路陥没です。</li>
          </ol>
        </div>
      )}
    </section>
  );
}
