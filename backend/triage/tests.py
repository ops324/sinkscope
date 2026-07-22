"""triageアプリのテスト(Django標準TestCase、analysis/tests.pyと同じ流儀)。

確認するのは誠実性フレームワークが要求する4点:
  1. 疑似管路の生成が同一seedで完全に再現すること(決定性)
  2. 優先度算出(compute_priority_index/assign_tiers)がtierという順序尺度のみを
     生成し、連続スコアをそのままAPIへ漏らす構造になっていないこと
  3. baseline_correlation(道路長単独ベースラインとのSpearman順位相関)が
     -1〜1の妥当な範囲に収まること
  4. build.run()がMETHOD_VALIDATED=False・免責文をTriageRun.metrics_jsonへ
     必ず記録すること(手法免責の構造的保証。独立敵対的監査 guardrail (a))

Overpass APIへの実ネットワーク呼び出しは行わず、triage.pipes.fetch_roadsを
モックする。
"""
from unittest.mock import patch

from django.test import TestCase

from analysis.models import AnalysisRun
from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity, RoadExposure, SubsidenceEvent

from .build import run as run_triage
from .models import MeshPriority, SyntheticPipe, TriageRun
from .pipes import generate_synthetic_pipes
from .scoring import METHOD_VALIDATED, assign_tiers, baseline_correlation, compute_priority_index

TEST_BBOX = (139.80, 35.70, 139.81, 35.71)


def _fake_road_elements(cells):
    """テスト用メッシュの重心近傍を通る、短い道路way(2点)をメッシュ数だけ用意する。"""
    elements = []
    for i, cell in enumerate(cells):
        lon, lat = cell.centroid.x, cell.centroid.y
        elements.append(
            {
                "id": 1000 + i,
                "geometry": [
                    {"lon": lon - 0.0005, "lat": lat},
                    {"lon": lon + 0.0005, "lat": lat},
                ],
            }
        )
    return elements


class SyntheticPipeGenerationTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        self.assertGreater(len(self.cells), 1)

    def test_same_seed_is_deterministic(self):
        elements = _fake_road_elements(self.cells)
        with patch("triage.pipes.fetch_roads", return_value=elements):
            generate_synthetic_pipes(bbox=TEST_BBOX, seed=42)
            first = list(
                SyntheticPipe.objects.order_by("id").values_list(
                    "mesh_cell_id", "install_year", "pipe_material"
                )
            )
            generate_synthetic_pipes(bbox=TEST_BBOX, seed=42)
            second = list(
                SyntheticPipe.objects.order_by("id").values_list(
                    "mesh_cell_id", "install_year", "pipe_material"
                )
            )
        self.assertEqual(first, second)

    def test_pipes_are_flagged_synthetic(self):
        elements = _fake_road_elements(self.cells)
        with patch("triage.pipes.fetch_roads", return_value=elements):
            generate_synthetic_pipes(bbox=TEST_BBOX, seed=1)
        self.assertGreater(SyntheticPipe.objects.count(), 0)
        self.assertTrue(all(p.is_synthetic for p in SyntheticPipe.objects.all()))


class ScoringTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        for i, cell in enumerate(self.cells):
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.05 * i
            )
            RoadExposure.objects.create(mesh_cell=cell, road_length_m=100.0 * (i + 1))

    def _frame(self):
        from analysis.features import build_summary_frame

        frame = build_summary_frame(fiscal_year="2025")
        frame["pipe_count"] = 0
        return frame

    def test_tiers_are_only_ordinal_labels(self):
        scored = assign_tiers(compute_priority_index(self._frame()))
        self.assertTrue(set(scored["tier"].unique()) <= {"low", "medium", "high"})

    def test_baseline_correlation_within_valid_range(self):
        scored = compute_priority_index(self._frame())
        rho = baseline_correlation(scored)
        self.assertIsNotNone(rho)
        self.assertGreaterEqual(rho, -1.0)
        self.assertLessEqual(rho, 1.0)

    def test_method_validated_is_false(self):
        # 独立敵対的監査の中心的指摘：本プロジェクトの検定は仮説を支持しなかった
        # ため、手法は常に未検証としてマークされていなければならない。
        self.assertFalse(METHOD_VALIDATED)


class TriageBuildTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        for i, cell in enumerate(self.cells):
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.05 * i
            )
            RoadExposure.objects.create(mesh_cell=cell, road_length_m=100.0 * (i + 1))
        SubsidenceEvent.objects.create(
            mesh_cell=self.cells[0],
            geom=self.cells[0].centroid,
            location_text="テストイベント",
            cause_facility="下水道",
        )
        # method_validation_noteはMonitorの最新AnalysisRunからその場で組み立てられる
        # (独立敵対的監査の指摘: 以前はp値を固定文字列で持っており、Monitorの検定が
        # 再実行されても追随しなかった)。ここでは「仮説不支持」のAnalysisRunを用意し、
        # その結果がTriage側の免責文に正しく反映されることを検証する。
        AnalysisRun.objects.create(
            fiscal_year="2025",
            metrics_json={
                "permutation_test": {
                    "skipped": False,
                    "p_value_one_sided": 0.962,
                }
            },
        )

    def test_run_records_method_disclaimer_and_baseline_correlation(self):
        elements = _fake_road_elements(self.cells)
        with patch("triage.pipes.fetch_roads", return_value=elements):
            run_obj = run_triage(seed=42)

        self.assertIsInstance(run_obj, TriageRun)
        self.assertFalse(run_obj.metrics_json["method_validated"])
        self.assertIn("支持しませんでした", run_obj.metrics_json["method_validation_note"])
        self.assertIn("0.962", run_obj.metrics_json["method_validation_note"])
        self.assertIn("baseline_road_length_spearman_rho", run_obj.metrics_json)
        self.assertGreater(run_obj.metrics_json["pipe_count"], 0)

        priorities = MeshPriority.objects.filter(run=run_obj)
        self.assertGreater(priorities.count(), 0)
        for p in priorities:
            self.assertIn(p.tier, {"low", "medium", "high"})

    def test_method_disclaimer_reflects_latest_monitor_run_not_a_fixed_string(self):
        # Monitorの検定が再実行され結果が変われば(例: 仮説を支持する方向のp値)、
        # Triage側の免責文もその場で追随することを確認する
        # (「片側p=0.962」の固定文字列だった過去のリグレッションを防ぐ回帰テスト)。
        AnalysisRun.objects.create(
            fiscal_year="2026",
            metrics_json={
                "permutation_test": {
                    "skipped": False,
                    "p_value_one_sided": 0.01,
                }
            },
        )
        elements = _fake_road_elements(self.cells)
        with patch("triage.pipes.fetch_roads", return_value=elements):
            run_obj = run_triage(seed=42)

        note = run_obj.metrics_json["method_validation_note"]
        self.assertIn("支持しました", note)
        self.assertIn("0.010", note)

    def test_existing_pipes_are_reused_without_refetch(self):
        elements = _fake_road_elements(self.cells)
        with patch("triage.pipes.fetch_roads", return_value=elements) as mocked_fetch:
            run_triage(seed=42)
            self.assertEqual(mocked_fetch.call_count, 1)
            run_triage(seed=42)  # regenerate_pipes=False (既定) なら再フェッチしない
            self.assertEqual(mocked_fetch.call_count, 1)
