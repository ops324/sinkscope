import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  fetchEvents,
  fetchMeshSummary,
  type EventFeatureProperties,
  type EventsResponse,
  type MeshFeatureProperties,
  type MeshSummaryResponse,
} from "../api/client";
import Legend from "../components/Legend";
import { elevationColor, landUseColor, landUseLabel, roadLengthColor, velocityColor } from "./colors";
import { LAYER_LABELS, type LayerKey } from "./types";

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

export default function MonitorMap() {
  const [activeLayer, setActiveLayer] = useState<LayerKey>("velocity");
  const [meshData, setMeshData] = useState<MeshSummaryResponse | null>(null);
  const [eventsData, setEventsData] = useState<EventsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    fetchMeshSummary()
      .then(setMeshData)
      .catch((err: unknown) => setLoadError(String(err)));
    fetchEvents()
      .then(setEventsData)
      .catch((err: unknown) => setLoadError(String(err)));
  }, []);

  const layers = useMemo(() => {
    const built = [];

    if (meshData) {
      built.push(
        new GeoJsonLayer<MeshFeatureProperties>({
          id: "mesh-summary",
          data: meshData.features,
          filled: true,
          stroked: true,
          getFillColor: (f: GeoJSON.Feature<GeoJSON.Geometry, MeshFeatureProperties>) =>
            fillColorForLayer(activeLayer, f.properties),
          getLineColor: [30, 34, 38, 90] as [number, number, number, number],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          pickable: true,
          updateTriggers: { getFillColor: activeLayer },
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

    return built;
  }, [meshData, eventsData, activeLayer]);

  return (
    <div className="monitor-map">
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller
        layers={layers}
        getTooltip={({ object, layer }) => {
          if (!object) return null;
          if (layer?.id === "mesh-summary") return { text: meshTooltipText(object.properties) };
          if (layer?.id === "subsidence-events") return { text: eventTooltipText(object.properties) };
          return null;
        }}
      >
        <Map mapStyle={GSI_PALE_STYLE} />
      </DeckGL>

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

      <Legend activeLayer={activeLayer} />

      {loadError && <div className="map-error">データ取得に失敗しました: {loadError}</div>}
    </div>
  );
}
