"""OpenStreetMapの道路網から、メッシュ単位の道路延長を取り込む。

道路延長は資産そのものではなく、陥没報告密度モデルにおける「曝露(exposure)」
オフセットとして使う――報告件数は本質的に道路が長い/交通量が多いメッシュほど
多くなりやすいため、その effect を補正するために必要な実データ。
"""
from __future__ import annotations

from collections import defaultdict

import requests
from django.contrib.gis.geos import LineString

from core.aoi import DEMO_AOI_BBOX
from core.mesh import PROJECTED_SRID, STORAGE_SRID, ensure_mesh_cells
from core.models import MeshCell, RoadExposure

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Overpass APIの利用ガイドラインに従い、識別可能なUser-Agentを付与する
# (UA無し/genericなUAは406 Not Acceptableで拒否される)。
REQUEST_HEADERS = {"User-Agent": "SinkScope/0.1 (+https://github.com/ops324/sinkscope)"}

# 陥没リスクの文脈で意味のある道路種別(歩道・私道等の細道は対象外)
HIGHWAY_TAGS = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
]


def _overpass_query(bbox: tuple[float, float, float, float]) -> str:
    west, south, east, north = bbox
    tags = "|".join(HIGHWAY_TAGS)
    return (
        "[out:json][timeout:180];"
        f'way["highway"~"^({tags})$"]({south},{west},{north},{east});'
        "out geom;"
    )


def fetch_roads(bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX) -> list[dict]:
    """Overpass APIから対象エリアの道路ウェイ(geometry込み)を取得する。"""
    response = requests.post(
        OVERPASS_URL, data={"data": _overpass_query(bbox)}, headers=REQUEST_HEADERS, timeout=200
    )
    response.raise_for_status()
    return response.json()["elements"]


def ingest_roads(bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX) -> int:
    """道路網を取得し、メッシュごとの道路延長[m]をRoadExposureへ保存する。"""
    ensure_mesh_cells(bbox)
    elements = fetch_roads(bbox)

    length_by_cell: dict[int, float] = defaultdict(float)
    for element in elements:
        coords = element.get("geometry")
        if not coords or len(coords) < 2:
            continue
        line = LineString([(pt["lon"], pt["lat"]) for pt in coords], srid=STORAGE_SRID)

        for cell in MeshCell.objects.filter(geom__intersects=line):
            clipped = line.intersection(cell.geom)
            if clipped.empty:
                continue
            clipped.srid = STORAGE_SRID
            clipped.transform(PROJECTED_SRID)
            length_by_cell[cell.id] += clipped.length

    for cell_id, length_m in length_by_cell.items():
        RoadExposure.objects.update_or_create(
            mesh_cell_id=cell_id,
            defaults={"road_length_m": length_m, "source": "osm"},
        )
    return len(length_by_cell)
