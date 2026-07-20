import "./App.css";

function App() {
  return (
    <div className="page">
      <header className="header">
        <h1>SinkScope</h1>
        <p className="subtitle">地盤沈下モニタリング＆下水道点検トリアージ</p>
      </header>

      <blockquote className="positioning">
        検出科学（陥没そのものの検知）では競わない ― そこはNTT等の研究開発の領分。
        公開衛星データ → 自治体が使えるGIS意思決定レイヤーのラストマイルをE2Eで実証する。
      </blockquote>

      <div className="modules">
        <section className="module">
          <h2>Monitor</h2>
          <p>
            100%実データ。国土地理院の衛星SAR地盤変動測量成果、地盤沈下の加速度・トレンド変化検出、
            道路陥没オープンデータとの空間相関検証。
          </p>
        </section>
        <section className="module">
          <h2>Triage</h2>
          <p>
            Monitorの実成果をメッシュ単位の点検優先度に翻訳する意思決定支援層。
            疑似管路データは Illustrative バッジで明示し、実データと隔離する。
          </p>
        </section>
      </div>

      <p className="status">Monitor / Triage の実装は今後のPRで追加されます。</p>
    </div>
  );
}

export default App;
