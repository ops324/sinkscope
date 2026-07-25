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
  const [selectedMesh, setSelectedMesh] = useState<MeshFeatureProperties | null>(null);
  const [meshLoading, setMeshLoading] = useState(true);
  // Triage行→地図連動(D5)のフォーカス区画。Monitorの selectedMesh とは別チャネル:
  // Triage行は完全な MeshFeatureProperties を持たず、地図ハイライトに要る mesh_code だけ扱う。
  const [triageFocusCode, setTriageFocusCode] = useState<string | null>(null);
  // 地図に実在するメッシュコード集合。triage/ranking(TriageRun)と mesh/summary(AnalysisRun)は
  // 別runなので、地図に無い行を非インタラクティブ化して「押せるのに無反応」を防ぐ。
  const [availableMeshCodes, setAvailableMeshCodes] = useState<Set<string>>(() => new Set());

  function handleModuleChange(next: ModuleView) {
    setModuleView(next);
    // Triageへ切替時は Monitor/Triage 双方の選択を解除(異なるデータ文脈の混在を避ける)。
    if (next !== "monitor") setSelectedMesh(null);
    if (next === "monitor") setTriageFocusCode(null);
  }

  // Monitorでは実データ選択、Triageでは行連動フォーカスを地図ハイライトに渡す。
  const highlightMeshCode = moduleView === "monitor" ? selectedMesh?.mesh_code ?? null : triageFocusCode;

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
          selectedMeshCode={highlightMeshCode}
          onSelectMesh={setSelectedMesh}
          onMeshLoadingChange={setMeshLoading}
          onMeshCodesLoaded={setAvailableMeshCodes}
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
          <TriagePanel
            selectedMeshCode={triageFocusCode}
            availableMeshCodes={availableMeshCodes}
            onSelectRow={(code) => setTriageFocusCode((prev) => (prev === code ? null : code))}
          />
        )}
      </div>
    </div>
  );
}

export default App;
