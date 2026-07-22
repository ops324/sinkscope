import { useState } from "react";

import "./App.css";
import HonestyPanel from "./components/HonestyPanel";
import TriagePanel from "./components/TriagePanel";
import MonitorMap from "./map/MonitorMap";
import { MODULE_VIEW_LABELS, type ModuleView } from "./map/types";

function App() {
  const [moduleView, setModuleView] = useState<ModuleView>("monitor");

  return (
    <div className="app">
      <header className="app-header">
        <h1>SinkScope</h1>
        <p className="subtitle">
          地盤沈下モニタリング＆下水道点検トリアージ ― {MODULE_VIEW_LABELS[moduleView]}
        </p>
        <div className="module-switcher">
          {(Object.keys(MODULE_VIEW_LABELS) as ModuleView[]).map((key) => (
            <button
              key={key}
              type="button"
              className={key === moduleView ? "active" : ""}
              onClick={() => setModuleView(key)}
            >
              {MODULE_VIEW_LABELS[key]}
            </button>
          ))}
        </div>
      </header>

      <div className="app-body">
        <MonitorMap moduleView={moduleView} />
        {moduleView === "monitor" ? <HonestyPanel /> : <TriagePanel />}
      </div>
    </div>
  );
}

export default App;
