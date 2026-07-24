import { useState } from "react";

import "./App.css";
import type { MeshFeatureProperties } from "./api/client";
import HonestyPanel from "./components/HonestyPanel";
import MapGuide from "./components/MapGuide";
import MeshDetailPanel from "./components/MeshDetailPanel";
import TriagePanel from "./components/TriagePanel";
import MonitorMap from "./map/MonitorMap";
import { MODULE_VIEW_LABELS, type ModuleView } from "./map/types";

function App() {
  const [moduleView, setModuleView] = useState<ModuleView>("monitor");
  // 選択中メッシュは App が source of truth として保持する(地図クリック→右レール詳細)。
  // 将来 D4(検索→flyTo/選択)・D5(Triage行→地図連動)からも同じ選択状態を駆動できる。
  const [selectedMesh, setSelectedMesh] = useState<MeshFeatureProperties | null>(null);
  const [meshLoading, setMeshLoading] = useState(true);

  function handleModuleChange(next: ModuleView) {
    setModuleView(next);
    // Triageへ切替時は Monitor の選択を解除(異なるデータ文脈の混在を避ける)。
    if (next !== "monitor") setSelectedMesh(null);
  }

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
              onClick={() => handleModuleChange(key)}
            >
              {MODULE_VIEW_LABELS[key]}
            </button>
          ))}
        </div>
      </header>

      <div className="app-body">
        <MonitorMap
          moduleView={moduleView}
          selectedMeshCode={selectedMesh?.mesh_code ?? null}
          onSelectMesh={setSelectedMesh}
          onMeshLoadingChange={setMeshLoading}
        />
        {moduleView === "monitor" ? (
          <div className="monitor-rail">
            <MapGuide />
            <MeshDetailPanel
              selected={selectedMesh}
              loading={meshLoading}
              onClear={() => setSelectedMesh(null)}
            />
            <HonestyPanel />
          </div>
        ) : (
          <TriagePanel />
        )}
      </div>
    </div>
  );
}

export default App;
