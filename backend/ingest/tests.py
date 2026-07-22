"""ingest（Djangoアプリではなく取込スクリプト群）のテスト。

来歴汚染バグ(F9: `gsi_displacement.py`の`FISCAL_YEAR = "2025"`ハードコード)の
修正を検証する:
  1. `_current_fiscal_year` がJST基準で年度境界を正しく判定すること
     （UTCのまま判定すると4/1 00:00 JST付近で1年ズレる回帰を防ぐ）
  2. `_derive_fiscal_year` が実ファイル名フォーマット未観測のため常にNoneを返す
     こと（導出を凍結している設計判断の明示。docs/SPEC.md §4.1参照）
  3. 同一ラスタ（同一content_sha256）の再取込が`DisplacementAcquisition`を
     重複作成せず、`DisplacementVelocity.acquisition`が同一の取得記録を
     指し続けること（ネットワークはモックし、合成GeoTIFFを使う）
"""
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest import mock

import numpy as np
import rasterio
import rasterio.io
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rasterio.transform import from_origin

from core.mesh import ensure_mesh_cells
from core.models import DisplacementAcquisition, DisplacementVelocity

from .gsi_displacement import (
    _FetchResult,
    _current_fiscal_year,
    _derive_fiscal_year,
    ingest_displacement_velocity,
)

# analysis/api配下の既存テストと同じ小さなAOI(実際のensure_mesh_cellsで複数メッシュが
# 生成される程度の大きさ)。
TEST_BBOX = (139.80, 35.70, 139.805, 35.705)


def _build_test_geotiff_bytes(
    bbox: tuple[float, float, float, float],
    value: float,
    resolution_deg: float = 0.0002,
    pad_deg: float = 0.004,
) -> bytes:
    """テスト用の単一バンド定数値GeoTIFFを合成する。

    ingest側は`dataset.transform`と`cell.geom.extent`（STORAGE_SRIDの経緯度）を
    直接突き合わせるだけで再投影は行わないため、CRSの値自体は機能に影響しない。
    `pad_deg`は、bboxに対してensure_mesh_cellsが生成する250mメッシュがbbox境界の
    外側まで（グリッド整列の都合で最大250m弱）はみ出し得る分を十分に覆うための余白。
    """
    west, south, east, north = bbox
    west, south, east, north = west - pad_deg, south - pad_deg, east + pad_deg, north + pad_deg
    width = max(1, int((east - west) / resolution_deg))
    height = max(1, int((north - south) / resolution_deg))
    transform = from_origin(west, north, resolution_deg, resolution_deg)
    array = np.full((height, width), value, dtype="float32")

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(array, 1)
        return memfile.read()


class CurrentFiscalYearTests(SimpleTestCase):
    """UTCのまま年度判定すると、JSTの年度境界(4/1 00:00)付近で1年ズレる回帰を防ぐ。"""

    def test_just_after_jst_new_fiscal_year_boundary(self):
        # 2026-03-31 15:30 UTC == 2026-04-01 00:30 JST → 新年度(2026)。
        dt = datetime(2026, 3, 31, 15, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(_current_fiscal_year(dt), "2026")

    def test_just_before_jst_new_fiscal_year_boundary(self):
        # 2026-03-31 14:30 UTC == 2026-03-31 23:30 JST → まだ旧年度(2025)。
        dt = datetime(2026, 3, 31, 14, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(_current_fiscal_year(dt), "2025")

    def test_naive_datetime_is_used_as_is(self):
        dt = datetime(2026, 4, 1, 0, 0)
        self.assertEqual(_current_fiscal_year(dt), "2026")


class DeriveFiscalYearTests(SimpleTestCase):
    """実ファイル名フォーマットが未観測のため、導出ロジックは凍結されている(常にNone)。

    年トークンらしき文字列を含む入力でも、誤って一意確定させないことを確認する
    （実フォーマット判明前に緩い正規表現で「それらしい」年度を拾うことの危険性は
    敵対的監査で指摘された。docs/SPEC.md §4.1参照）。
    """

    def test_returns_none_even_with_year_like_tokens(self):
        file_info = {"file_name": "R7_20250401_qu.zip", "zip_path": "sar/2025/qu.zip"}
        self.assertIsNone(_derive_fiscal_year(file_info, "merge_sbas_2025_qu.tif"))

    def test_returns_none_for_empty_input(self):
        self.assertIsNone(_derive_fiscal_year({}, ""))


class IngestDisplacementVelocityDedupTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        self.assertGreater(len(self.cells), 0, "テスト用AOIからメッシュが生成されること")

    @staticmethod
    def _fetch_result(value: float) -> _FetchResult:
        return _FetchResult(
            tif_bytes=_build_test_geotiff_bytes(TEST_BBOX, value=value),
            file_info={"file_name": "dummy.zip", "zip_path": "dummy/path", "cmd_types": ["3"]},
            tif_name="dummy.tif",
            retrieved_at=timezone.now(),
        )

    @mock.patch("ingest.gsi_displacement._fetch_velocity_geotiff")
    def test_reingesting_identical_raster_reuses_acquisition(self, mock_fetch):
        mock_fetch.return_value = self._fetch_result(value=-0.3)
        saved_first = ingest_displacement_velocity(bbox=TEST_BBOX)
        self.assertGreater(saved_first, 0)
        self.assertEqual(DisplacementAcquisition.objects.count(), 1)
        acquisition = DisplacementAcquisition.objects.get()
        self.assertEqual(acquisition.fiscal_year_provenance, "unverified_retrieval_time")

        # 同一content(同一hash)での再取込は、新規acquisitionを作らず既存を再利用する。
        mock_fetch.return_value = self._fetch_result(value=-0.3)
        saved_second = ingest_displacement_velocity(bbox=TEST_BBOX)

        self.assertEqual(saved_second, saved_first)
        self.assertEqual(
            DisplacementAcquisition.objects.count(),
            1,
            "同一contentの再取込でDisplacementAcquisitionが重複作成されないこと",
        )
        for velocity in DisplacementVelocity.objects.all():
            self.assertEqual(velocity.acquisition_id, acquisition.id)

    @mock.patch("ingest.gsi_displacement._fetch_velocity_geotiff")
    def test_different_content_creates_new_acquisition(self, mock_fetch):
        mock_fetch.return_value = self._fetch_result(value=-0.3)
        ingest_displacement_velocity(bbox=TEST_BBOX)

        mock_fetch.return_value = self._fetch_result(value=-0.9)
        ingest_displacement_velocity(bbox=TEST_BBOX, fiscal_year="2030")

        self.assertEqual(DisplacementAcquisition.objects.count(), 2)

    @mock.patch("ingest.gsi_displacement._fetch_velocity_geotiff")
    def test_explicit_fiscal_year_is_recorded_as_operator_override(self, mock_fetch):
        mock_fetch.return_value = self._fetch_result(value=-0.6)
        ingest_displacement_velocity(bbox=TEST_BBOX, fiscal_year="2031")

        acquisition = DisplacementAcquisition.objects.get()
        self.assertEqual(acquisition.fiscal_year, "2031")
        self.assertEqual(acquisition.fiscal_year_provenance, "operator_override")
        self.assertTrue(
            DisplacementVelocity.objects.filter(
                fiscal_year="2031", acquisition=acquisition
            ).exists()
        )
