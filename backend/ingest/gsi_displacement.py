"""国土地理院 衛星SAR地盤変動測量成果（干渉SAR時系列解析）の取込。

sarprod.gsi.go.jp の「データ範囲選択」機能が内部で呼んでいるAPI
(execCommand/ → downloadfile/) を直接呼び出し、対象エリアの準上下方向変位速度
GeoTIFFを取得する。このAPIはブラウザセッションに依存しないことを実機検証済み
(cookieなしのrequestsで完全に再現できる)。

GSIが提供するのは各年度時点での「変位速度」（観測期間全体を通じた線形トレンド、
cm/年、空間分解能約90m）であり、稠密な多時点の累積変位量ではない。取得した
ラスタを各MeshCell(250m)の範囲で平均し、DisplacementVelocityへ保存する。

**重要（docs/SPEC.md §4.1）**：このAPIには年度を選択するパラメータが無く、常に
「現在の年度成果」1枚のスナップショットを返す。したがって取込側が固定の年度
文字列を主張することはできない（かつてこのファイルには`FISCAL_YEAR = "2025"`
というハードコードが存在し、後日別ヴィンテージのラスタを取り込んでも常に
"2025"と誤ラベルしていた。これは来歴汚染バグであり、本モジュールはその修正版）。

代わりに、取得したGeoTIFFバイト列のSHA-256（`DisplacementAcquisition.content_sha256`）
を**真のヴィンテージ識別子**として毎回記録する。`fiscal_year`はあくまでbest-effortの
表示用ラベルであり、`fiscal_year_provenance`でその信頼度（filename由来／明示指定／
取得時刻からの未検証推定）を必ず併記する。同一ラスタ（同一hash）の再取得は
DisplacementAcquisitionを重複作成せず、既存の年度ラベルを上書きしない。
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import rasterio
import rasterio.io
import requests
from django.utils import timezone
from rasterio.windows import from_bounds

from core.aoi import DEMO_AOI_BBOX
from core.mesh import ensure_mesh_cells
from core.models import DisplacementAcquisition, DisplacementVelocity

REQUEST_HEADERS = {
    "User-Agent": "SinkScope/0.1 (+https://github.com/ops324/sinkscope)",
    "Content-Type": "application/json",
}
BASE_URL = "https://sarprod.gsi.go.jp"

# 干渉SAR時系列解析「準上下方向」変位速度データのコマンド種別。
# layers_for_sar.txt のレイヤー定義(id: merge_sbas_regular_japan_*_qu_u16)と対応。
QUASI_VERTICAL_TYPE = "3"


@dataclass(frozen=True)
class _FetchResult:
    """1回のAPI取得の生の結果。年度ラベル決定・監査記録の材料をすべて保持する。"""

    tif_bytes: bytes
    file_info: dict
    tif_name: str
    retrieved_at: datetime


def _fetch_velocity_geotiff(bbox: tuple[float, float, float, float]) -> _FetchResult:
    """execCommand→downloadfileの2段階APIを呼び、準上下方向変位速度GeoTIFFを取得する。"""
    west, south, east, north = bbox
    retrieved_at = timezone.now()
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
    return _FetchResult(
        tif_bytes=archive.read(tif_name),
        file_info=file_info,
        tif_name=tif_name,
        retrieved_at=retrieved_at,
    )


def _current_fiscal_year(dt: datetime) -> str:
    """取得時刻から日本の年度（4月始まり）を推定する。

    dtがaware datetimeの場合は必ずJSTへ変換してから年度を判定する。UTCのまま
    判定すると、年度境界（4/1 00:00 JST = 3/31 15:00 UTC）付近で1年ズレる
    （例: 4/1 00:30 JSTはUTCでは3/31 15:30 → month=3と誤判定し前年度になる）。

    この値はあくまで「取得時計の年度」であり、GSIの成果公開には数か月単位の
    ラグがある（例: 2025年度成果は2026年3月31日公開）ため、実際に配信されている
    成果の年度と一致する保証はない。呼び出し元は必ず
    fiscal_year_provenance="unverified_retrieval_time" として記録すること。
    """
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return str(local.year if local.month >= 4 else local.year - 1)


def _derive_fiscal_year(file_info: dict, tif_name: str) -> str | None:
    """execCommand応答（file_name/zip_path）またはZIP内エントリ名(tif_name)から
    年度を一意に導出できる場合のみ返す。導出できない、または確信が持てない場合はNone。

    **現状は常にNoneを返す（導出を凍結している）**。docs/SPEC.md §4.1に記す通り、
    GSIの実際のfile_name/zip_path/tif_nameの中身はまだ一度も実機で観測されていない。
    フォーマット不明のまま`20\\d{2}`や`R\\d+`のような緩い正規表現で「それらしい」年
    トークンを拾うと、観測期間の複数年表記（例: `..._2022_2024...`）や年度と無関係な
    数値（処理日・プロダクトコード等）を誤って年度と取り違えるリスクがある。これは
    ハードコード年度を残すより悪い——「導出した」という誤った確信を来歴に刻んでしまう。

    実際のファイル名フォーマットを実機で確認した後、このdocstringを更新のうえ、
    既知パターンに厳密一致するnamed groupでのみ導出を有効化すること。それまでは
    content_sha256 + retrieved_atが来歴の正であり、fiscal_yearは
    "unverified_retrieval_time" としてラベルされる（呼び出し元
    ingest_displacement_velocity を参照）。
    """
    # file_info, tif_name は導出ロジック有効化時に使用する（現状は未使用）。
    return None


def ingest_displacement_velocity(
    bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX,
    fiscal_year: str | None = None,
) -> int:
    """準上下方向変位速度を取得し、MeshCellごとに平均してDisplacementVelocityへ保存する。

    `fiscal_year`はAPIが選択できる値ではない。呼び出し側が明示指定しない限り、
    取得したラスタから導出する（現状は導出不能につき常にフォールバック）か、
    導出不能なら取得時点の年度を推定する。いずれの場合も真のヴィンテージ識別子は
    取得したGeoTIFFのcontent_sha256であり、DisplacementAcquisitionに監査記録として
    保存する（docs/SPEC.md §4.1、§5）。同一ラスタ（同一content_sha256）の再取得は
    重複排除し、既存のDisplacementAcquisitionとその年度ラベルを再利用する
    （そうしないと、公開ラグの下で同一ラスタの再取込のたびに異なる推定年度が
    刻まれ、latest_fiscal_year()の判定を汚染しかねない）。
    """
    cells = ensure_mesh_cells(bbox)
    fetch_result = _fetch_velocity_geotiff(bbox)
    content_sha256 = hashlib.sha256(fetch_result.tif_bytes).hexdigest()

    acquisition = DisplacementAcquisition.objects.filter(content_sha256=content_sha256).first()
    if acquisition is None:
        if fiscal_year is not None:
            resolved_year, provenance = fiscal_year, "operator_override"
        else:
            derived_year = _derive_fiscal_year(fetch_result.file_info, fetch_result.tif_name)
            if derived_year is not None:
                resolved_year, provenance = derived_year, "filename"
            else:
                resolved_year = _current_fiscal_year(fetch_result.retrieved_at)
                provenance = "unverified_retrieval_time"

        acquisition = DisplacementAcquisition.objects.create(
            content_sha256=content_sha256,
            retrieved_at=fetch_result.retrieved_at,
            fiscal_year=resolved_year,
            fiscal_year_provenance=provenance,
            api_file_name=fetch_result.file_info.get("file_name", ""),
            zip_path=fetch_result.file_info.get("zip_path", ""),
            tif_name=fetch_result.tif_name,
            bbox=list(bbox),
            raw_file_info=fetch_result.file_info,
            source="gsi_sar_tsa",
        )

    saved = 0
    with rasterio.io.MemoryFile(fetch_result.tif_bytes) as memfile, memfile.open() as dataset:
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
                fiscal_year=acquisition.fiscal_year,
                source="gsi_sar_tsa",
                defaults={
                    "velocity_cm_per_year": float(np.mean(sub)),
                    "acquisition": acquisition,
                },
            )
            saved += 1
    return saved
