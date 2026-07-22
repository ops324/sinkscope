"""analysisアプリのテスト。

Django標準のTestCase(pytestではなくこのプロジェクトの既存流儀に合わせる)。
確認するのは主に誠実性フレームワークが要求する点:
  1. build_summary_frameがmesh_code昇順で決定的であること
  2. run_permutation_testが同一seedで完全に再現すること
  3. run_permutation_testがイベント由来の列(event_count/sewer_event_count)を
     一切参照しないこと(反循環の構造的保証)
  4. morans_i_velocity(空間自己相関の記述的診断)が、自己相関のあるデータでは
     期待値より十分大きく、自己相関を壊したデータでは期待値近傍になること

来歴汚染バグ(F9)の修正に伴い、以下も確認する:
  5. latest_fiscal_year()が、未検証の推定年度(unverified_retrieval_time)に
     検証済みラベル(filename/operator_override)を追い越させないこと
  6. displacement_provenance()が、fiscal_yearからの後付け参照ではなく、
     frameに実際に集約されたDisplacementVelocity行が指すacquisitionを返すこと
"""
import random
from datetime import timedelta

import pandas as pd
from django.test import TestCase
from django.utils import timezone

from core.mesh import _mesh_code, ensure_mesh_cells
from core.models import DisplacementAcquisition, DisplacementVelocity, GroundClass, RoadExposure

from .features import build_summary_frame, displacement_provenance, latest_fiscal_year
from .permutation import morans_i_velocity, run_permutation_test

# 250mメッシュが複数生成される程度の小さなAOI(実際のensure_mesh_cellsを使い、
# 手組みのポリゴンではなく本物の格子ロジックでテスト用メッシュを作る)。
TEST_BBOX = (139.80, 35.70, 139.81, 35.71)


class BuildSummaryFrameTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        self.assertGreater(len(self.cells), 1, "テスト用AOIから複数メッシュが生成されること")
        for i, cell in enumerate(self.cells):
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.05 * i
            )
            GroundClass.objects.create(mesh_cell=cell, land_use_class="0700", elevation_m=1.0 + i)
            RoadExposure.objects.create(mesh_cell=cell, road_length_m=100.0 * (i + 1))

    def test_frame_is_sorted_by_mesh_code(self):
        frame = build_summary_frame(fiscal_year="2025")
        self.assertEqual(list(frame["mesh_code"]), sorted(frame["mesh_code"]))

    def test_frame_is_deterministic_across_calls(self):
        frame_a = build_summary_frame(fiscal_year="2025")
        frame_b = build_summary_frame(fiscal_year="2025")
        self.assertTrue(frame_a.equals(frame_b))


class PermutationTestReproducibility(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        self.assertGreater(len(self.cells), 4, "パーミュテーションに十分なプールサイズが必要")
        for i, cell in enumerate(self.cells):
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.02 * i
            )
            RoadExposure.objects.create(mesh_cell=cell, road_length_m=150.0)

    def test_same_seed_gives_identical_result(self):
        frame = build_summary_frame(fiscal_year="2025")
        sewer_ids = {self.cells[0].id, self.cells[1].id}

        result_a = run_permutation_test(frame, sewer_ids, n_permutations=500, seed=7)
        result_b = run_permutation_test(frame, sewer_ids, n_permutations=500, seed=7)

        self.assertEqual(result_a, result_b)

    def test_different_seed_can_differ(self):
        frame = build_summary_frame(fiscal_year="2025")
        sewer_ids = {self.cells[0].id, self.cells[1].id}

        result_a = run_permutation_test(frame, sewer_ids, n_permutations=500, seed=1)
        result_b = run_permutation_test(frame, sewer_ids, n_permutations=500, seed=2)

        # 異なるseedでも観測統計量(observed_stat)自体は同じ(データに依存し乱数に依存しない)。
        self.assertEqual(
            result_a["observed_mean_diff_cm_per_year"], result_b["observed_mean_diff_cm_per_year"]
        )

    def test_ignores_event_count_columns(self):
        """反循環の構造的保証：event_count/sewer_event_countを列から落としても
        検定結果が変わらないこと(＝これらの列を一切参照していないこと)を確認する。
        """
        frame = build_summary_frame(fiscal_year="2025")
        sewer_ids = {self.cells[0].id}

        frame_without_events = frame.drop(columns=["event_count", "sewer_event_count"])

        result_with = run_permutation_test(frame, sewer_ids, n_permutations=300, seed=3)
        result_without = run_permutation_test(frame_without_events, sewer_ids, n_permutations=300, seed=3)

        self.assertEqual(result_with, result_without)

    def test_result_includes_morans_i_diagnostic(self):
        """run_permutation_testの返り値にMoran's I診断キーが含まれること
        （一様null自体は変更しない：既存の3テストが無改変で通ることがその裏付け）。
        """
        frame = build_summary_frame(fiscal_year="2025")
        sewer_ids = {self.cells[0].id, self.cells[1].id}

        result = run_permutation_test(frame, sewer_ids, n_permutations=300, seed=3)

        self.assertIn("morans_i", result)
        self.assertIn("morans_i_expected", result)
        self.assertIn("p_value_interpretation", result)
        self.assertIsInstance(result["p_value_interpretation"], str)
        self.assertGreater(len(result["p_value_interpretation"]), 0)


class MoransIVelocityTests(TestCase):
    """morans_i_velocity単体の振る舞い（DB不要、合成pd.DataFrameで直接検証）。

    独立敵対的監査の結論どおり、Moran's Iは有意性判定やnull補正には使わない記述的
    診断であるため、ここでは「自己相関のある/ないデータで妥当な値を返すか」
    「退化ケースでNoneを返すか」のみを確認する。
    """

    def _grid_pool(self, n: int = 8) -> tuple[pd.DataFrame, list[float]]:
        codes = [_mesh_code(ix, iy) for ix in range(n) for iy in range(n)]
        # 滑らかな速度勾配：隣接セルは常に近い値を取る＝強い正の自己相関を持つ合成データ。
        velocities = [-0.1 * (ix + iy) for ix in range(n) for iy in range(n)]
        return pd.DataFrame({"mesh_code": codes, "velocity_cm_per_year": velocities}), velocities

    def test_positive_on_autocorrelated_gradient(self):
        pool, _ = self._grid_pool()
        morans_i = morans_i_velocity(pool)
        expected = -1.0 / (len(pool) - 1)

        self.assertIsNotNone(morans_i)
        self.assertGreater(morans_i, expected)
        self.assertGreater(morans_i, 0.5, "滑らかな勾配は強い正の自己相関を持つはず")

    def test_near_expected_when_spatial_structure_destroyed(self):
        """mesh_codeへの速度値の対応づけを、RNGではなく固定seedのPython random.Random
        （プロセス依存のhash()には頼らない、完全に再現可能な決定的シャッフル）で崩し、
        空間構造のないデータではMoran's Iが期待値近傍になることを確認する。
        """
        pool, velocities = self._grid_pool()
        gradient_i = morans_i_velocity(pool)

        shuffled = velocities[:]
        random.Random(2024).shuffle(shuffled)
        shuffled_pool = pool.assign(velocity_cm_per_year=shuffled)
        shuffled_i = morans_i_velocity(shuffled_pool)
        expected = -1.0 / (len(pool) - 1)

        self.assertIsNotNone(shuffled_i)
        self.assertLess(
            abs(shuffled_i - expected),
            abs(gradient_i - expected),
            "空間構造を壊した後は勾配データよりも期待値に近いはず",
        )
        self.assertAlmostEqual(shuffled_i, expected, delta=0.3)

    def test_none_when_pool_too_small(self):
        pool = pd.DataFrame({"mesh_code": [_mesh_code(0, 0)], "velocity_cm_per_year": [1.0]})
        self.assertIsNone(morans_i_velocity(pool))

    def test_none_when_velocity_has_zero_variance(self):
        codes = [_mesh_code(ix, iy) for ix in range(4) for iy in range(4)]
        pool = pd.DataFrame({"mesh_code": codes, "velocity_cm_per_year": [1.0] * len(codes)})
        self.assertIsNone(morans_i_velocity(pool))

    def test_none_when_no_adjacent_cells(self):
        """セル同士が遠く離れて隣接ペアが一つも無い（S0=0）場合はNoneを返す。"""
        codes = [_mesh_code(ix * 100, 0) for ix in range(5)]
        pool = pd.DataFrame({"mesh_code": codes, "velocity_cm_per_year": list(range(5))})
        self.assertIsNone(morans_i_velocity(pool))


class LatestFiscalYearSelectionTests(TestCase):
    """未検証の推定年度が、検証済みラベルを追い越して`latest_fiscal_year()`を
    乗っ取らないことを確認する(来歴汚染バグF9の再発パターンへの回帰防止)。
    """

    def test_verified_provenance_is_preferred_over_more_recent_unverified(self):
        DisplacementAcquisition.objects.create(
            content_sha256="a" * 64,
            retrieved_at=timezone.now() - timedelta(days=400),
            fiscal_year="2025",
            fiscal_year_provenance="filename",
            bbox=list(TEST_BBOX),
        )
        DisplacementAcquisition.objects.create(
            content_sha256="b" * 64,
            retrieved_at=timezone.now(),
            fiscal_year="2027",
            fiscal_year_provenance="unverified_retrieval_time",
            bbox=list(TEST_BBOX),
        )

        # retrieved_atはunverifiedの方が新しいが、大小(文字列 or 日付)ではなく
        # 検証済みラベルが優先されること。
        self.assertEqual(latest_fiscal_year(), "2025")

    def test_falls_back_to_latest_retrieved_when_none_verified(self):
        DisplacementAcquisition.objects.create(
            content_sha256="c" * 64,
            retrieved_at=timezone.now() - timedelta(days=1),
            fiscal_year="2026",
            fiscal_year_provenance="unverified_retrieval_time",
            bbox=list(TEST_BBOX),
        )
        newest = DisplacementAcquisition.objects.create(
            content_sha256="d" * 64,
            retrieved_at=timezone.now(),
            fiscal_year="2027",
            fiscal_year_provenance="unverified_retrieval_time",
            bbox=list(TEST_BBOX),
        )

        self.assertEqual(latest_fiscal_year(), newest.fiscal_year)

    def test_falls_back_to_distinct_max_when_no_acquisitions_exist(self):
        """acquisitionが1件も無い(直接DisplacementVelocityを生成した)旧データ・
        既存テストとの後方互換を確認する。
        """
        cells = ensure_mesh_cells(TEST_BBOX)
        self.assertGreaterEqual(len(cells), 2)
        DisplacementVelocity.objects.create(
            mesh_cell=cells[0], fiscal_year="2024", velocity_cm_per_year=0.0
        )
        DisplacementVelocity.objects.create(
            mesh_cell=cells[1], fiscal_year="2026", velocity_cm_per_year=0.0
        )

        self.assertEqual(latest_fiscal_year(), "2026")


class DisplacementProvenanceTests(TestCase):
    """displacement_provenance()が、fiscal_year単位の後付け参照ではなく、
    frameに実際に集約されたDisplacementVelocity行のacquisitionを返すことを確認する。
    """

    def test_provenance_reflects_acquisition_actually_used_by_frame(self):
        cells = ensure_mesh_cells(TEST_BBOX)
        acquisition = DisplacementAcquisition.objects.create(
            content_sha256="e" * 64,
            retrieved_at=timezone.now(),
            fiscal_year="2025",
            fiscal_year_provenance="filename",
            bbox=list(TEST_BBOX),
        )
        for cell in cells:
            DisplacementVelocity.objects.create(
                mesh_cell=cell,
                fiscal_year="2025",
                velocity_cm_per_year=-0.1,
                acquisition=acquisition,
            )

        frame = build_summary_frame(fiscal_year="2025")
        provenance = displacement_provenance(frame)

        self.assertEqual(provenance["fiscal_year"], "2025")
        self.assertEqual(len(provenance["acquisitions"]), 1)
        self.assertEqual(provenance["acquisitions"][0]["content_sha256"], acquisition.content_sha256)
        self.assertEqual(
            provenance["acquisitions"][0]["fiscal_year_provenance"], "filename"
        )

    def test_empty_acquisitions_when_velocity_rows_have_no_acquisition_fk(self):
        cells = ensure_mesh_cells(TEST_BBOX)
        for cell in cells:
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.1
            )

        frame = build_summary_frame(fiscal_year="2025")
        provenance = displacement_provenance(frame)

        self.assertEqual(provenance["acquisitions"], [])
