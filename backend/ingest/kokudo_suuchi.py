"""国土数値情報（KSJ）土地利用細分メッシュ（L03-b）の取込。

KSJは1次メッシュ(約80km四方)単位で配布されており、対象エリア(DEMO_AOI_BBOX)は
1次メッシュコード"5339"1枚に収まる。各1次メッシュファイルには100m細分メッシュの
土地利用ポリゴンが数十万件含まれるため、素朴に全件をDBへ格納するのではなく、
各MeshCell(250m)の中心にどの細分メッシュが重なるかで代表的な土地利用種別を決め、
GroundClass.land_use_classへ集約して保存する。

KSJのメッシュコード命名規則(L03-b-{年度}_{1次メッシュ4桁}-{測地系}_GML.zip)は
実際にデータリストページのHTMLを取得して確認済み。文字コード問題を避けるため、
zip同梱のGeoJSON(UTF-8)を読む――同梱のDBF(シェープファイル属性)はShift-JISだが
使わない。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import requests
from django.conf import settings
from django.contrib.gis.geos import Polygon
from shapely import wkb

from core.aoi import DEMO_AOI_BBOX
from core.mesh import PROJECTED_SRID
from core.models import GroundClass, MeshCell

REQUEST_HEADERS = {"User-Agent": "SinkScope/0.1 (+https://github.com/ops324/sinkscope)"}

# 対象エリア(DEMO_AOI_BBOX)を覆う1次メッシュ。年度は最新(2021年="21")、測地系はJGD2011。
PRIMARY_MESH_CODE = "5339"
LAND_USE_URL = (
    f"https://nlftp.mlit.go.jp/ksj/gml/data/L03-b/L03-b-21/"
    f"L03-b-21_{PRIMARY_MESH_CODE}-jgd2011_GML.zip"
)


def _cache_dir() -> Path:
    """生データのキャッシュ先(settings.RAW_DATA_DIR/ksj)。

    以前は絶対パス"/data/raw/ksj"を直書きしており、コンテナ外(ローカル開発・CI)
    では存在しないディレクトリを指すため再現不能だった。settings.RAW_DATA_DIR
    (既定はリポジトリ直下data/raw、Docker Compose環境では/data/rawへ.envで
    上書き)を都度参照することで、環境を問わず一貫させる。関数化しているのは、
    Django設定が読み込まれる前にモジュールレベルで評価されるのを避けるため。
    """
    return settings.RAW_DATA_DIR / "ksj"


def _download_or_cached(url: str, cache_path: Path) -> bytes:
    if cache_path.exists():
        return cache_path.read_bytes()

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=120)
    response.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return response.content


def _load_land_use_geodataframe() -> gpd.GeoDataFrame:
    zip_bytes = _download_or_cached(LAND_USE_URL, _cache_dir() / f"L03-b-21_{PRIMARY_MESH_CODE}.zip")
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    geojson_name = next(n for n in archive.namelist() if n.endswith(".geojson"))
    return gpd.read_file(io.BytesIO(archive.read(geojson_name)))


def _mesh_cells_geodataframe(bbox) -> gpd.GeoDataFrame:
    cells = MeshCell.objects.filter(centroid__within=_bbox_polygon(bbox))
    records = [
        {"mesh_cell_id": cell.id, "geometry": wkb.loads(bytes(cell.geom.wkb))} for cell in cells
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:6668")


def _bbox_polygon(bbox):
    return Polygon.from_bbox(bbox)


def ingest_land_use(bbox=DEMO_AOI_BBOX) -> int:
    """土地利用細分メッシュを取込み、MeshCellごとの代表土地利用種別をGroundClassへ保存する。"""
    land_use = _load_land_use_geodataframe()
    # 重心計算は地理座標系(度)では歪むため、平面直角座標系へ投影してから求める
    centroid_projected = land_use.geometry.to_crs(PROJECTED_SRID).centroid
    centroid_geographic = centroid_projected.to_crs(land_use.crs)
    centroids = gpd.GeoDataFrame(
        {"land_use_class": land_use["土地利用種別"]}, geometry=centroid_geographic, crs=land_use.crs
    )

    mesh_cells = _mesh_cells_geodataframe(bbox)
    joined = gpd.sjoin(centroids, mesh_cells, predicate="within")

    # メッシュごとに最頻の土地利用種別を代表値として採用する
    majority = joined.groupby("mesh_cell_id")["land_use_class"].agg(lambda s: s.mode().iat[0])

    saved = 0
    for mesh_cell_id, land_use_class in majority.items():
        GroundClass.objects.update_or_create(
            mesh_cell_id=mesh_cell_id,
            defaults={"land_use_class": land_use_class, "source_year": 2021},
        )
        saved += 1
    return saved
