import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { FlyToInterpolator, type MapViewState } from "@deck.gl/core";
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  fetchEvents,
  fetchMeshSummary,
  fetchTriagePipes,
  type EventFeatureProperties,
  type EventsResponse,
  type MeshFeatureProperties,
  type MeshSummaryResponse,
  type TriagePipeFeatureProperties,
  type TriagePipesResponse,
} from "../api/client";
import Legend from "../components/Legend";
import { elevationColor, landUseColor, landUseLabel, roadLengthColor, tierColor, velocityColor } from "./colors";
import { LAYER_LABELS, type LayerKey, type ModuleView } from "./types";

// 江東区・江戸川区・八潮市周辺(core/aoi.pyのDEMO_AOI_BBOXと同じ対象エリア)を初期表示。
const INITIAL_VIEW_STATE = {
  longitude: 139.855,
  latitude: 35.735,
  zoom: 11.3,
  pitch: 0,
  bearing: 0,
};

// 国土地理院 淡色地図タイル(認証不要、来歴がデータソースと一貫している)。
const GSI_PALE_STYLE = {
  version: 8 as const,
  sources: {
    gsi: {
      type: "raster" as const,
      tiles: ["https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution:
        '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">国土地理院</a>',
    },
  },
  layers: [{ id: "gsi-pale", type: "raster" as const, source: "gsi", minzoom: 0, maxzoom: 18 }],
};

const SEWER_CAUSE = "下水道";
const SEWER_EVENT_COLOR: [number, number, number, number] = [255, 90, 30, 235];
const OTHER_EVENT_COLOR: [number, number, number, number] = [225, 225, 225, 170];

function fillColorForLayer(layerKey: LayerKey, props: MeshFeatureProperties) {
  switch (layerKey) {
    case "velocity":
      return velocityColor(props.velocity_cm_per_year);
    case "elevation":
      return elevationColor(props.elevation_m);
    case "road_length":
      return roadLengthColor(props.road_length_m);
    case "land_use":
      return landUseColor(props.land_use_class);
    default:
      return [0, 0, 0, 0] as [number, number, number, number];
  }
}

function meshTooltipText(props: MeshFeatureProperties): string {
  const velocity =
    props.velocity_cm_per_year === null
      ? "データなし"
      : `${props.velocity_cm_per_year.toFixed(3)} cm/年`;
  const elevation = props.elevation_m === null ? "データなし" : `${props.elevation_m.toFixed(2)} m`;
  const road = props.road_length_m === null ? "データなし" : `${Math.round(props.road_length_m)} m`;
  return [
    `メッシュ: ${props.mesh_code}`,
    `変位速度(実測): ${velocity}`,
    `土地利用: ${landUseLabel(props.land_use_class)}`,
    `標高: ${elevation}`,
    `道路延長: ${road}`,
    `陥没報告: ${props.event_count}件（うち下水道原因 ${props.sewer_event_count}件）`,
  ].join("\n");
}

function eventTooltipText(props: EventFeatureProperties): string {
  return [
    props.location_text,
    `年度: ${props.fiscal_year} / 要因施設: ${props.cause_facility || "不明"}`,
    `位置精度: ${props.geocode_confidence}（字・大字レベルのジオコーディング。同一字は同一座標）`,
  ].join("\n");
}

function pipeTooltipText(props: TriagePipeFeatureProperties): string {
  return [
    "疑似管路（Illustrative・架空データ）",
    `メッシュ: ${props.mesh_code}`,
    `点検優先度tier: ${props.tier ?? "データなし"}（未検証の手法によるヒューリスティック）`,
    `架空の布設年: ${props.install_year} / 架空の管種: ${props.pipe_material}`,
  ].join("\n");
}

// メッシュポリゴンのbbox中心(≒重心。メッシュは小さな矩形なので実用上十分)を返す。
// 型は GeoJSON.Polygon 固定(api/client.ts)。coordinates は number[][][](リング→点→[lng,lat])
// なので .flat() で点列 number[][] にしてから集計する(.flat(2)にすると座標が壊れNaNになる)。
function bboxCenter(geometry: GeoJSON.Polygon): [number, number] {
  const points = geometry.coordinates.flat();
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const [lng, lat] of points) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [(minLng + maxLng) / 2, (minLat + maxLat) / 2];
}

// transition プロパティを取り除いた素の viewState。制御 viewState に transitionInterpolator を
// 永続させると deck が「遷移中」のままになり操作(パン/ズーム/クリック)が固まる。遷移完了時と
// ユーザー操作時にこれで素の状態へ戻し、遷移プロパティを必ず一過性にする。
function plainViewState(v: MapViewState): MapViewState {
  return {
    longitude: v.longitude,
    latitude: v.latitude,
    zoom: v.zoom,
    pitch: v.pitch ?? 0,
    bearing: v.bearing ?? 0,
  };
}

// Triage行連動ロケータの中立配色(発散/赤/tier紫=ハザード配色は使わない。監査制約#3)。
// 破線=Illustrative文法を保ちつつ、密な疑似管路レイヤーの中でも選択セルを見つけられるよう、
// 淡い中立フィルで「面」を出し、明るいクリスプ破線で縁取る。中立白系はハザード含意を持たない。
const LOCATOR_FILL: [number, number, number, number] = [236, 242, 248, 55];
const LOCATOR_LINE: [number, number, number, number] = [245, 249, 252, 245];
const LOCATOR_HALO: [number, number, number, number] = [30, 36, 44, 150];

export default function MonitorMap({
  moduleView,
  selectedMeshCode,
  onSelectMesh,
  onMeshLoadingChange,
  onMeshCodesLoaded,
}: {
  moduleView: ModuleView;
  selectedMeshCode: string | null;
  onSelectMesh: (props: MeshFeatureProperties | null) => void;
  onMeshLoadingChange: (loading: boolean) => void;
  onMeshCodesLoaded?: (codes: Set<string>) => void;
}) {
  const [activeLayer, setActiveLayer] = useState<LayerKey>("velocity");
  const [meshData, setMeshData] = useState<MeshSummaryResponse | null>(null);
  const [eventsData, setEventsData] = useState<EventsResponse | null>(null);
  const [pipesData, setPipesData] = useState<TriagePipesResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // flyTo(Triage行連動)のため viewState を制御する。initialViewState(非制御)のままだと
  // カメラをプログラムから動かせない。MapViewState は transition プロパティ
  // (transitionDuration/Interpolator/onTransitionEnd)も内包するので、そのまま状態型に使う
  // (推論型 = INITIAL_VIEW_STATE のリテラル型のままだと excess-property でビルドが落ちる)。
  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);

  useEffect(() => {
    fetchMeshSummary()
      .then((data) => {
        setMeshData(data);
        // triage/ranking(TriageRun)の行が地図に実在するか判定できるよう、コード集合を通知。
        onMeshCodesLoaded?.(new Set(data.features.map((f) => f.properties.mesh_code)));
      })
      .catch((err: unknown) => setLoadError(String(err)))
      .finally(() => onMeshLoadingChange(false));
    fetchEvents()
      .then(setEventsData)
      .catch((err: unknown) => setLoadError(String(err)));
  }, [onMeshLoadingChange, onMeshCodesLoaded]);

  // 選択中メッシュのfeature(中立色ハイライト用)。source of truthはApp側のselectedMeshCode。
  const selectedFeature = useMemo(() => {
    if (!meshData || selectedMeshCode === null) return null;
    return meshData.features.find((f) => f.properties.mesh_code === selectedMeshCode) ?? null;
  }, [meshData, selectedMeshCode]);

  // 初見向けコーチマーク: まず何をすればよいか(区画クリック)を一度だけ促す。
  // 一度でも選択したら二度と出さない(邪魔しない)。手動で閉じることも可能。
  const [everSelected, setEverSelected] = useState(false);
  const [coachDismissed, setCoachDismissed] = useState(false);
  useEffect(() => {
    // コーチマークは Monitor のオンボーディング。Triage行連動でも selectedMeshCode が流れる
    // ため、Monitor 選択に限定して点火する(Triage操作で Monitor 初回導線を消さない)。
    if (moduleView === "monitor" && selectedMeshCode !== null) setEverSelected(true);
  }, [moduleView, selectedMeshCode]);
  const showCoach = moduleView !== "triage" && !!meshData && !everSelected && !coachDismissed;

  useEffect(() => {
    if (moduleView === "triage" && !pipesData) {
      fetchTriagePipes()
        .then(setPipesData)
        .catch((err: unknown) => setLoadError(String(err)));
    }
  }, [moduleView, pipesData]);

  const isTriage = moduleView === "triage";

  // Triageで行が選ばれたら、その区画へカメラを飛ばす(D5)。依存は selectedFeature に取る
  // ――selectedMeshCode だけだと meshData 遅延到着時に selectedFeature がまだ null で、
  // 後から埋まっても再実行されず飛ばない(dead click)。トグル解除(null)や Monitor では飛ばさない。
  useEffect(() => {
    if (!isTriage || !selectedFeature) return;
    const [cx, cy] = bboxCenter(selectedFeature.geometry);
    setViewState((v) => ({
      ...v,
      longitude: cx,
      latitude: cy,
      // 上限付き。字・大字レベルのジオコーディング(粗い位置精度)を過大に「正確」に見せない。
      zoom: Math.min(Math.max(v.zoom, 12), 13),
      transitionDuration: 800,
      transitionInterpolator: new FlyToInterpolator(),
      // 遷移完了で遷移プロパティを破棄する(deck-timer駆動なのでユーザー操作が無くても発火)。
      // これを怠ると transitionInterpolator が残り、地図操作が固まる。
      onTransitionEnd: () => setViewState((cur) => plainViewState(cur)),
    }));
  }, [selectedFeature, isTriage]);

  const layers = useMemo(() => {
    const built = [];

    if (meshData) {
      built.push(
        new GeoJsonLayer<MeshFeatureProperties>({
          id: "mesh-summary",
          data: meshData.features,
          filled: true,
          stroked: true,
          // Triageビューでは実データのメッシュ配色を淡くし、Illustrativeなパイプ
          // レイヤーが視覚的な主役になるようにする(実データと合成データの混同防止)。
          getFillColor: (f: GeoJSON.Feature<GeoJSON.Geometry, MeshFeatureProperties>) =>
            isTriage ? [40, 44, 50, 60] : fillColorForLayer(activeLayer, f.properties),
          getLineColor: [30, 34, 38, 90] as [number, number, number, number],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          pickable: !isTriage,
          updateTriggers: { getFillColor: [activeLayer, isTriage] },
        }),
      );
    }

    // 選択セルの中立色ハイライト。「選択」を示すUIアフォーダンスとして、アプリ共通の
    // アクセント青(module/layerのactiveと同系)を用いる。発散/赤=危険配色は使わない(監査制約#3)。
    // 外側の淡いグロー＋内側のクリスプな芯の2枚で、縮尺に依らず「どのセルか」を一目で示す。
    // 選択セル1件だけを描く別レイヤーにし、全メッシュのfill再評価を避ける。
    if (selectedFeature && !isTriage) {
      built.push(
        new GeoJsonLayer<MeshFeatureProperties>({
          id: "mesh-selected-glow",
          data: [selectedFeature],
          filled: false,
          stroked: true,
          getLineColor: [74, 158, 255, 90] as [number, number, number, number],
          getLineWidth: 7,
          lineWidthUnits: "pixels",
          pickable: false,
        }),
        new GeoJsonLayer<MeshFeatureProperties>({
          id: "mesh-selected-core",
          data: [selectedFeature],
          filled: false,
          stroked: true,
          getLineColor: [235, 242, 250, 255] as [number, number, number, number],
          getLineWidth: 2.5,
          lineWidthUnits: "pixels",
          pickable: false,
        }),
      );
    }

    // Triage の行連動ハイライト(D5)は Monitor のソリッド青枠を流用しない。このコードベース
    // 確立の「破線=Illustrative」文法(疑似管路レイヤーと同じ)に合わせ、中立灰の破線ロケータに
    // する――架空ワークリストの位置指示であって、実測ハザードの再着色ではないことを示す。
    if (selectedFeature && isTriage) {
      built.push(
        // 淡い中立フィル+暗いハロー(コントラスト確保)。密な破線パイプの中でも面で視認できる。
        new GeoJsonLayer<MeshFeatureProperties>({
          id: "mesh-triage-locator-fill",
          data: [selectedFeature],
          filled: true,
          stroked: true,
          getFillColor: LOCATOR_FILL,
          getLineColor: LOCATOR_HALO,
          getLineWidth: 5,
          lineWidthUnits: "pixels",
          pickable: false,
        }),
        // 明るいクリスプ破線の縁取り(破線=Illustrative文法)。中立白系でハザード含意なし。
        new GeoJsonLayer<
          MeshFeatureProperties,
          PathStyleExtensionProps<GeoJSON.Feature<GeoJSON.Geometry, MeshFeatureProperties>>
        >({
          id: "mesh-triage-locator",
          data: [selectedFeature],
          filled: false,
          stroked: true,
          getLineColor: LOCATOR_LINE,
          getLineWidth: 2.5,
          lineWidthUnits: "pixels",
          getDashArray: [6, 3],
          dashJustified: true,
          extensions: [new PathStyleExtension({ dash: true })],
          pickable: false,
        }),
      );
    }

    if (eventsData) {
      built.push(
        new ScatterplotLayer({
          id: "subsidence-events",
          data: eventsData.features,
          getPosition: (f: GeoJSON.Feature<GeoJSON.Point, EventFeatureProperties>) =>
            f.geometry.coordinates as [number, number],
          getFillColor: (f: GeoJSON.Feature<GeoJSON.Point, EventFeatureProperties>) =>
            f.properties.cause_facility === SEWER_CAUSE ? SEWER_EVENT_COLOR : OTHER_EVENT_COLOR,
          getLineColor: [20, 20, 20, 200] as [number, number, number, number],
          stroked: true,
          lineWidthMinPixels: 1,
          getRadius: 45,
          radiusMinPixels: 4,
          radiusMaxPixels: 11,
          pickable: true,
        }),
      );
    }

    if (isTriage && pipesData) {
      built.push(
        new PathLayer<
          GeoJSON.Feature<GeoJSON.LineString, TriagePipeFeatureProperties>,
          PathStyleExtensionProps<GeoJSON.Feature<GeoJSON.LineString, TriagePipeFeatureProperties>>
        >({
          id: "synthetic-pipes",
          data: pipesData.features,
          getPath: (f: GeoJSON.Feature<GeoJSON.LineString, TriagePipeFeatureProperties>) =>
            f.geometry.coordinates as [number, number][],
          // 破線で描画し、実データの道路延長レイヤー(実線)とは明確に異なる見た目にする
          // (疑似管路=Illustrativeであることの視覚的な常設シグナル)。
          getColor: (f: GeoJSON.Feature<GeoJSON.LineString, TriagePipeFeatureProperties>) =>
            tierColor(f.properties.tier),
          getWidth: 3,
          widthMinPixels: 1.5,
          widthMaxPixels: 4,
          getDashArray: [3, 2],
          dashJustified: true,
          extensions: [new PathStyleExtension({ dash: true })],
          pickable: true,
        }),
      );
    }

    return built;
  }, [meshData, eventsData, pipesData, activeLayer, isTriage, selectedFeature]);

  return (
    <div className="monitor-map">
      <DeckGL
        viewState={viewState}
        // 制御モードでは echo に徹する(throttle/分岐/早期returnするとカメラが中間位置で凍る)。
        // 素の viewState に戻すことで、残存しうる遷移プロパティをユーザー操作時に確実に消す。
        onViewStateChange={({ viewState: next }) => setViewState(plainViewState(next as MapViewState))}
        controller
        layers={layers}
        getCursor={({ isDragging, isHovering }) =>
          isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
        }
        onClick={(info) => {
          // メッシュをクリック→選択(右レール詳細)。同じセルを再クリック→選択解除(トグル)。
          // 陥没イベント点のクリックは選択を変えない(層IDで判定)。
          // 背景クリックはdeckのオーバーレイ構成ではonClickが発火しないため、解除は
          // トグル再クリックとパネルの「解除」ボタン(App側 onClear)で担保する。
          if (isTriage) return;
          if (info.object && info.layer?.id === "mesh-summary") {
            const props = (info.object as GeoJSON.Feature<GeoJSON.Geometry, MeshFeatureProperties>)
              .properties;
            onSelectMesh(props.mesh_code === selectedMeshCode ? null : props);
          }
        }}
        getTooltip={({ object, layer }) => {
          if (!object) return null;
          if (layer?.id === "mesh-summary" && !isTriage) return { text: meshTooltipText(object.properties) };
          if (layer?.id === "subsidence-events") return { text: eventTooltipText(object.properties) };
          if (layer?.id === "synthetic-pipes") return { text: pipeTooltipText(object.properties) };
          return null;
        }}
      >
        <Map mapStyle={GSI_PALE_STYLE} />
      </DeckGL>

      {isTriage && (
        <div className="illustrative-banner">
          <span className="illustrative-badge">Illustrative</span>
          疑似管路・点検優先度は架空データ・未検証の手法です（詳細は右パネル）
        </div>
      )}

      {!isTriage && (
        <div className="layer-switcher">
          {(Object.keys(LAYER_LABELS) as LayerKey[]).map((key) => (
            <button
              key={key}
              type="button"
              className={key === activeLayer ? "active" : ""}
              onClick={() => setActiveLayer(key)}
            >
              {LAYER_LABELS[key]}
            </button>
          ))}
        </div>
      )}

      {showCoach && (
        <div className="map-coach" role="status">
          <span className="map-coach-text">
            <span aria-hidden="true">👆</span> 気になる区画をクリック
            <span className="map-coach-sub">→ 右で実測値を確認できます</span>
          </span>
          <button
            type="button"
            className="map-coach-close"
            aria-label="ヒントを閉じる"
            onClick={() => setCoachDismissed(true)}
          >
            ✕
          </button>
        </div>
      )}

      <Legend activeLayer={activeLayer} showTriageLegend={isTriage} />

      {loadError && <div className="map-error">データ取得に失敗しました: {loadError}</div>}
    </div>
  );
}
