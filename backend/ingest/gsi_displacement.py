"""国土地理院 衛星SAR地盤変動測量成果（干渉SAR時系列解析）の取込。

sarprod.gsi.go.jp の「データ範囲選択」機能が内部で呼んでいるAPI
(execCommand/ → downloadfile/) を直接呼び出し、対象エリアの準上下方向変位速度
GeoTIFFを取得する。このAPIはブラウザセッションに依存しないことを実機検証済み
(cookieなしのrequestsで完全に再現できる)。

GSIが提供するのは各年度時点での「変位速度」（観測期間全体を通じた線形トレンド、
cm/年、空間分解能約90m）であり、稠密な多時点の累積変位量ではない。取得した
ラスタを各MeshCell(250m)の範囲で平均し、DisplacementVelocityへ保存する。
年度ごとに別レコードとして保存するため、後日別年度の成果(例:「2023年度成果」)
を同じ関数で取り込めば、年度間の速度差からトレンド変化を検出できる。
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import rasterio
import rasterio.io
import requests
from rasterio.windows import from_bounds

from core.aoi import DEMO_AOI_BBOX
from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity

REQUEST_HEADERS = {
    "User-Agent": "SinkScope/0.1 (+https://github.com/ops324/sinkscope)",
    "Content-Type": "application/json",
}
BASE_URL = "https://sarprod.gsi.go.jp"

# 干渉SAR時系列解析「準上下方向」変位速度データのコマンド種別。
# layers_for_sar.txt のレイヤー定義(id: merge_sbas_regular_japan_*_qu_u16)と対応。
QUASI_VERTICAL_TYPE = "3"
FISCAL_YEAR = "2025"  # 2026年3月31日公開、だいち4号の観測データを反映した最新成果


def _fetch_velocity_geotiff(bbox: tuple[float, float, float, float]) -> bytes:
    """execCommand→downloadfileの2段階APIを呼び、準上下方向変位速度GeoTIFFを取得する。"""
    west, south, east, north = bbox
    exec_response = requests.post(
        f"{BASE_URL}/execCommand/",
        headers=REQUEST_HEADERS,
        json={"type": [QUASI_VERTICAL_TYPE], "coordinates": [west, east, south, north]},
        timeout=60,
    )
    exec_response.raise_for_status()
    file_info = exec_response.json()

    download_response = requests.post(
        f"{BASE_URL}/downloadfile/",
        headers=REQUEST_HEADERS,
        json={"file_info": file_info},
        timeout=60,
    )
    download_response.raise_for_status()

    archive = zipfile.ZipFile(io.BytesIO(download_response.content))
    tif_name = next(n for n in archive.namelist() if n.endswith(".tif"))
    return archive.read(tif_name)


def ingest_displacement_velocity(
    bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX,
    fiscal_year: str = FISCAL_YEAR,
) -> int:
    """準上下方向変位速度を取得し、MeshCellごとに平均してDisplacementVelocityへ保存する。"""
    cells = ensure_mesh_cells(bbox)
    tif_bytes = _fetch_velocity_geotiff(bbox)

    saved = 0
    with rasterio.io.MemoryFile(tif_bytes) as memfile, memfile.open() as dataset:
        array = dataset.read(1)
        nodata = dataset.nodata

        for cell in cells:
            west, south, east, north = cell.geom.extent
            window = from_bounds(west, south, east, north, transform=dataset.transform)
            window = window.round_offsets().round_lengths()
            row_off, col_off = max(0, int(window.row_off)), max(0, int(window.col_off))
            row_end = min(dataset.height, row_off + max(1, int(window.height)))
            col_end = min(dataset.width, col_off + max(1, int(window.width)))
            if row_end <= row_off or col_end <= col_off:
                continue

            sub = array[row_off:row_end, col_off:col_end]
            if nodata is not None:
                sub = sub[sub != nodata]
            if sub.size == 0:
                continue

            DisplacementVelocity.objects.update_or_create(
                mesh_cell=cell,
                fiscal_year=fiscal_year,
                source="gsi_sar_tsa",
                defaults={"velocity_cm_per_year": float(np.mean(sub))},
            )
            saved += 1
    return saved
