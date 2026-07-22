"""analysisアプリのテスト。

Django標準のTestCase(pytestではなくこのプロジェクトの既存流儀に合わせる)。
確認するのは主に誠実性フレームワークが要求する3点:
  1. build_summary_frameがmesh_code昇順で決定的であること
  2. run_permutation_testが同一seedで完全に再現すること
  3. run_permutation_testがイベント由来の列(event_count/sewer_event_count)を
     一切参照しないこと(反循環の構造的保証)

来歴汚染バグ(F9)の修正に伴い、以下も確認する:
  4. latest_fiscal_year()が、未検証の推定年度(unverified_retrieval_time)に
     検証済みラベル(filename/operator_override)を追い越させないこと
  5. displacement_provenance()が、fiscal_yearからの後付け参照ではなく、
     frameに実際に集約されたDisplacementVelocity行が指すacquisitionを返すこと
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.mesh import ensure_mesh_cells
from core.models import DisplacementAcquisition, DisplacementVelocity, GroundClass, RoadExposure

from .features import build_summary_frame, displacement_provenance, latest_fiscal_year
from .permutation import run_permutation_test

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
