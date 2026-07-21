"""analysisアプリのテスト。

Django標準のTestCase(pytestではなくこのプロジェクトの既存流儀に合わせる)。
確認するのは主に誠実性フレームワークが要求する3点:
  1. build_summary_frameがmesh_code昇順で決定的であること
  2. run_permutation_testが同一seedで完全に再現すること
  3. run_permutation_testがイベント由来の列(event_count/sewer_event_count)を
     一切参照しないこと(反循環の構造的保証)
"""
from django.test import TestCase

from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity, GroundClass, RoadExposure

from .features import build_summary_frame
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
