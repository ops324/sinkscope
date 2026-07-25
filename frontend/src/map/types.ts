export type LayerKey = "velocity" | "land_use" | "elevation" | "road_length";

export const LAYER_LABELS: Record<LayerKey, string> = {
  velocity: "変位速度 (cm/年)",
  land_use: "土地利用",
  elevation: "標高 (m)",
  road_length: "道路延長 (m)",
};

// Monitor(100%実データ) / Triage(疑似管路・点検優先度、Illustrative)のビュー切替。
export type ModuleView = "monitor" | "triage";

export const MODULE_VIEW_LABELS: Record<ModuleView, string> = {
  monitor: "Monitor",
  triage: "Triage (Illustrative)",
};
