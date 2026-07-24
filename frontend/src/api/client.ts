// backend/api/ のエンドポイントに対するfetchヘルパ。
//
// mesh/summary と events は「実データ」をそのまま返す(予測・スコアは含まない)。
// analysis/run/latest だけが推論結果(付録検定・n実測値)を返し、HonestyPanelが
// これを直接描画する。バックエンド側の設計意図は backend/api/views.py 参照。
//
// triage/pipes と triage/ranking はTriage(意思決定支援層)のIllustrativeな
// レスポンス。連続スコア(priority_index)は型にも存在しない――tier(高/中/低)のみを
// 公開する(独立敵対的監査 guardrail (b))。

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
      // 空間自己相関の記述的診断（有意性検定・null補正には用いない）。
      // 隣接セル間で変位速度が似た値を取る度合いを示す大域Moran's I。
      // 自己相関なしの期待値は-1/(n-1)。データ不足等でNoneになりうる。
      morans_i: number | null;
      morans_i_expected: number | null;
      // p_value_one_sided/two_sidedが「空間自己相関を無視した反保守的な下限値」で
      // あることを平易に説明する一文（backend/analysis/permutation.py参照）。
      p_value_interpretation: string;
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

// Triage: 順序尺度(高/中/低)のみ。priority_index等の連続スコアは型に存在しない。
export type TriageTier = "low" | "medium" | "high";

export type TriagePipeFeatureProperties = {
  illustrative: true;
  method_validated: false;
  mesh_code: string;
  install_year: number;
  pipe_material: string;
  tier: TriageTier | null;
};

export type TriagePipesResponse = {
  type: "FeatureCollection";
  run: { id: number; created_at: string } | null;
  features: GeoJSON.Feature<GeoJSON.LineString, TriagePipeFeatureProperties>[];
  disclaimers: string[];
};

export type TriageRankingRow = {
  mesh_code: string;
  tier: TriageTier;
  velocity_cm_per_year: number | null;
  road_length_m: number | null;
  sewer_event_count: number;
  pipe_count: number;
};

export type TriageMetrics = {
  method_validated: false;
  method_validation_note: string;
  pipe_count: number;
  eligible_mesh_count: number;
  baseline_road_length_spearman_rho: number | null;
};

export type TriageRankingResponse =
  | { exists: false; ranking: []; disclaimers: string[] }
  | {
      exists: true;
      run_id: number;
      created_at: string;
      seed: number;
      weights: Record<string, number> | null;
      metrics: TriageMetrics;
      ranking: TriageRankingRow[];
      disclaimers: string[];
    };

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`API request failed: ${path} (${response.status})`);
  }
  return response.json() as Promise<T>;
}

// 単一URL配信(D7): 静的モードでは、コミット済みの焼き固めJSON(frontend/public/data/*.json、
// backend の export_static コマンドが本物のview関数から生成)を同一オリジンから読み、サーバ・DBに
// 一切アクセスしない。これで GitHub Pages 等の静的ホスティングにそのまま置ける。
// VITE_DATA_SOURCE=static のビルド(npm run build:static)でのみ有効で、通常の dev(npm run dev)や
// build ではライブAPI(/api/)を叩くため既存挙動は不変。取得先は import.meta.env.BASE_URL 起点にし、
// 配信 base が "/" でも "/sinkscope/" でも正しく解決させる(相対パスによるワーカーURL解決問題を回避)。
const STATIC_DATA = import.meta.env.VITE_DATA_SOURCE === "static";

function endpoint(staticFile: string, livePath: string): string {
  return STATIC_DATA ? `${import.meta.env.BASE_URL}data/${staticFile}` : livePath;
}

export function fetchMeshSummary(): Promise<MeshSummaryResponse> {
  return getJSON(endpoint("mesh-summary.json", "/api/mesh/summary/"));
}

export function fetchEvents(causeFacility?: string): Promise<EventsResponse> {
  // 静的モードは全イベントの焼き固めJSONを返す。cause_facility での絞り込みは呼び出し側
  // (MonitorMap.tsx の色分け)が担うため、パラメータなしの1ファイルで足りる。
  if (STATIC_DATA) {
    return getJSON(endpoint("events.json", "/api/events/"));
  }
  const query = causeFacility ? `?cause_facility=${encodeURIComponent(causeFacility)}` : "";
  return getJSON(`/api/events/${query}`);
}

export function fetchAnalysisRunLatest(): Promise<AnalysisRunLatestResponse> {
  return getJSON(endpoint("analysis-run-latest.json", "/api/analysis/run/latest/"));
}

export function fetchTriagePipes(): Promise<TriagePipesResponse> {
  return getJSON(endpoint("triage-pipes.json", "/api/triage/pipes/"));
}

export function fetchTriageRanking(): Promise<TriageRankingResponse> {
  return getJSON(endpoint("triage-ranking.json", "/api/triage/ranking/"));
}

// 地名検索(D4)の候補。名称＋座標のみで、スコア・予測は含まない。
export type GeocodeCandidate = {
  title: string;
  longitude: number;
  latitude: number;
};

// 国土地理院 地名検索API。イベント座標のジオコード(ingest/kanbotsu_xlsx.py)や地図タイルと
// 同じ来歴(国土地理院)で、CORS許可済みのためブラウザから直接呼べる。連続スコアは扱わない。
// 全国の候補を返すため、AOI内への絞り込みは呼び出し側の責務(core/aoi.py の DEMO_AOI_BBOX)。
export async function fetchGeocode(query: string): Promise<GeocodeCandidate[]> {
  const url = `https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Geocode request failed (${response.status})`);
  }
  const data = (await response.json()) as Array<{
    geometry: { coordinates: [number, number] };
    properties: { title: string };
  }>;
  return data
    .filter((f) => Array.isArray(f.geometry?.coordinates))
    .map((f) => ({
      title: f.properties.title,
      longitude: f.geometry.coordinates[0],
      latitude: f.geometry.coordinates[1],
    }));
}
