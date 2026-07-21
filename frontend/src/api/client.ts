// backend/api/ の3エンドポイントに対するfetchヘルパ。
//
// mesh/summary と events は「実データ」をそのまま返す(予測・スコアは含まない)。
// analysis/run/latest だけが推論結果(付録検定・n実測値)を返し、HonestyPanelが
// これを直接描画する。バックエンド側の設計意図は backend/api/views.py 参照。

export type MeshFeatureProperties = {
  mesh_code: string;
  velocity_cm_per_year: number | null;
  land_use_class: string;
  elevation_m: number | null;
  road_length_m: number | null;
  event_count: number;
  sewer_event_count: number;
};

export type MeshSummaryResponse = {
  type: "FeatureCollection";
  run: { id: number; fiscal_year: string } | null;
  features: GeoJSON.Feature<GeoJSON.Polygon, MeshFeatureProperties>[];
};

export type EventFeatureProperties = {
  fiscal_year: string;
  prefecture: string;
  location_text: string;
  road_name: string;
  cause_facility: string;
  road_jurisdiction: string;
  geocode_confidence: string;
};

export type EventsResponse = {
  type: "FeatureCollection";
  note: string;
  features: GeoJSON.Feature<GeoJSON.Point, EventFeatureProperties>[];
};

export type PermutationTestResult =
  | { skipped: true; reason: string }
  | {
      skipped: false;
      hypothesis: string;
      unit_of_analysis: string;
      eligible_pool_size: number;
      k_sewer_cells: number;
      observed_mean_diff_cm_per_year: number;
      n_permutations: number;
      seed: number;
      p_value_one_sided: number;
      p_value_two_sided: number;
      underpowered: boolean;
      limitation_note: string;
    };

export type AnalysisRunMetrics = {
  in_aoi_event_count: number;
  in_aoi_sewer_event_count: number;
  occupied_oaza_count: number;
  occupied_oaza_sewer_count: number;
  permutation_test_min_n: number;
  permutation_test_eligible: boolean;
  permutation_test: PermutationTestResult;
};

export type AnalysisRunLatestResponse =
  | { exists: false; disclaimers: string[] }
  | {
      exists: true;
      run_id: number;
      created_at: string;
      fiscal_year: string;
      metrics: AnalysisRunMetrics;
      disclaimers: string[];
    };

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`API request failed: ${path} (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function fetchMeshSummary(): Promise<MeshSummaryResponse> {
  return getJSON("/api/mesh/summary/");
}

export function fetchEvents(causeFacility?: string): Promise<EventsResponse> {
  const query = causeFacility ? `?cause_facility=${encodeURIComponent(causeFacility)}` : "";
  return getJSON(`/api/events/${query}`);
}

export function fetchAnalysisRunLatest(): Promise<AnalysisRunLatestResponse> {
  return getJSON("/api/analysis/run/latest/");
}
