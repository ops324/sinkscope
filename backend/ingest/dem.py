"""国土地理院 標高タイル（地理院タイル、認証不要）の取込。

基盤地図情報の生GML DEMはservice.gsi.go.jp/kibanでの利用者登録(無料だが氏名・住所等の
入力が必要)を要するため、代わりに認証不要でHTTP直接取得できる標高タイル(PNG)を使う。
エンコード仕様は https://maps.gsi.go.jp/development/demtile.html の一次情報を直接
(生HTMLで<sup>タグを確認して)検証済み:

    x = 2^16 R + 2^8 G + B
    x <  2^23  ->  h = x * u
    x == 2^23  ->  h = NA (無効値。(R,G,B)=(128,0,0)がこれに一致)
    x >  2^23  ->  h = (x - 2^24) * u
    u = 0.01 (分解能m)

ズームレベルはDEM5A/5B/5Cのネイティブ解像度(5m)に対応するzoom=15を使う。
DEM5A(航空レーザ、最高精度)から順に試し、タイルが存在しない(404)場合は
DEM5B、さらにDEM10B(全国網羅)へフォールバックする。
"""
from __future__ import annotations

import math

import rasterio
import rasterio.io
import requests

from core.aoi import DEMO_AOI_BBOX
from core.mesh import ensure_mesh_cells
from core.models import GroundClass, MeshCell

REQUEST_HEADERS = {"User-Agent": "SinkScope/0.1 (+https://github.com/ops324/sinkscope)"}
ZOOM = 15
TILE_SIZE = 256
RESOLUTION_M = 0.01
NODATA_X = 128 * 65536  # (R,G,B)=(128,0,0) -> x=2^23、demtile.htmlで無効値と明記

# 精度の高い順。個々のタイル単位で404ならフォールバックする。
DATASETS = ("dem5a_png", "dem5b_png", "dem_png")


def _lonlat_to_tile_pixel(lon: float, lat: float, zoom: int = ZOOM) -> tuple[int, int, int, int]:
    lat_rad = math.radians(lat)
    n = 2**zoom
    x_f = (lon + 180.0) / 360.0 * n
    y_f = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    x_tile, y_tile = int(x_f), int(y_f)
    px = int((x_f - x_tile) * TILE_SIZE)
    py = int((y_f - y_tile) * TILE_SIZE)
    return x_tile, y_tile, px, py


def _decode_elevation(r: int, g: int, b: int) -> float | None:
    x = 65536 * r + 256 * g + b
    if x == NODATA_X:
        return None
    if x < NODATA_X:
        return x * RESOLUTION_M
    return (x - 16777216) * RESOLUTION_M


def _fetch_tile(x_tile: int, y_tile: int, zoom: int = ZOOM):
    """優先度順にデータセットを試し、最初に取得できたタイルのRGB配列を返す。"""
    for dataset in DATASETS:
        url = f"https://cyberjapandata.gsi.go.jp/xyz/{dataset}/{zoom}/{x_tile}/{y_tile}.png"
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        with rasterio.io.MemoryFile(response.content) as memfile:
            with memfile.open() as dataset_reader:
                return dataset_reader.read()
    return None


def ingest_elevation(bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX) -> int:
    """各MeshCellの中心点の標高を取得し、GroundClass.elevation_mへ保存する。"""
    cells = ensure_mesh_cells(bbox)

    cells_by_tile: dict[tuple[int, int], list[tuple[MeshCell, int, int]]] = {}
    for cell in cells:
        x_tile, y_tile, px, py = _lonlat_to_tile_pixel(cell.centroid.x, cell.centroid.y)
        cells_by_tile.setdefault((x_tile, y_tile), []).append((cell, px, py))

    saved = 0
    for (x_tile, y_tile), cell_pixels in cells_by_tile.items():
        array = _fetch_tile(x_tile, y_tile)
        if array is None:
            continue
        for cell, px, py in cell_pixels:
            r, g, b = array[0, py, px], array[1, py, px], array[2, py, px]
            elevation = _decode_elevation(int(r), int(g), int(b))
            if elevation is None:
                continue
            GroundClass.objects.update_or_create(
                mesh_cell=cell, defaults={"elevation_m": elevation}
            )
            saved += 1
    return saved
