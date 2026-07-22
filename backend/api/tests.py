"""api アプリのテスト(Django標準TestCase)。

誠実性フレームワークが要求する2点を確認する:
  1. /api/events/ がAOI外(mesh_cellが紐づかない)イベントを返さないこと
  2. /api/mesh/summary/ が「ハザードスコア」的なフィールドを一切含まず、
     実データの集約のみを返すこと(docs/SPEC.md §7参照)

/api/triage/* については、独立敵対的監査 guardrail を構造的に保証する:
  3. /api/triage/pipes/ の各地物が illustrative=True・method_validated=False を
     持つこと(「データ」だけでなく「手法」も未検証であることの免責)
  4. /api/triage/ranking/ が priority_index 等の連続スコアを一切含まないこと
     (tierという順序尺度のみを公開する)
  5. 両エンドポイントの disclaimers に「未検証」の趣旨が含まれること
  6. /api/triage/ranking/ の並び順がtier(高→中→低)・tier内mesh_code昇順であり、
     priority_index降順とは独立であること(guardrail (b)の実装漏れの回帰防止。
     tierだけへの縮約がAPIの並び順から骨抜きにされていないことの保証)
"""
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TestCase

from analysis.models import AnalysisRun, MeshSummary
from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity, RoadExposure, SubsidenceEvent
from triage.models import MeshPriority, TriageRun

TEST_BBOX = (139.80, 35.70, 139.805, 35.705)


class EventsApiTests(TestCase):
    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        SubsidenceEvent.objects.create(
            mesh_cell=self.cells[0],
            geom=self.cells[0].centroid,
            location_text="AOI内イベント",
            cause_facility="下水道",
        )
        SubsidenceEvent.objects.create(
            mesh_cell=None,
            geom=Point(140.5, 36.5, srid=6668),
            location_text="AOI外イベント",
            cause_facility="下水道",
        )

    def test_excludes_events_outside_aoi(self):
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        texts = [f["properties"]["location_text"] for f in data["features"]]

        self.assertIn("AOI内イベント", texts)
        self.assertNotIn("AOI外イベント", texts)


class MeshSummaryApiTests(TestCase):
    FORBIDDEN_KEYS = {
        "score",
        "hazard_score",
        "expected_event_rate",
        "risk",
        "risk_score",
        "hazard",
        "prediction",
    }
    EXPECTED_KEYS = {
        "mesh_code",
        "velocity_cm_per_year",
        "land_use_class",
        "elevation_m",
        "road_length_m",
        "event_count",
        "sewer_event_count",
    }

    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        run = AnalysisRun.objects.create(fiscal_year="2025")
        for cell in self.cells:
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=0.05
            )
            MeshSummary.objects.create(
                mesh_cell=cell,
                run=run,
                velocity_cm_per_year=0.05,
                land_use_class="0700",
                event_count=0,
                sewer_event_count=0,
            )

    def test_summary_contains_only_real_data_fields_no_score(self):
        response = self.client.get("/api/mesh/summary/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["features"]), 0)

        props = set(data["features"][0]["properties"].keys())
        self.assertEqual(props, self.EXPECTED_KEYS)
        self.assertFalse(props & self.FORBIDDEN_KEYS)


class TriageApiTests(TestCase):
    """独立敵対的監査 guardrail の構造的保証: /api/triage/* エンドポイント。"""

    FORBIDDEN_KEYS = {
        "priority_index",
        "score",
        "hazard_score",
        "risk_score",
        "expected_event_rate",
    }

    def setUp(self):
        self.cells = ensure_mesh_cells(TEST_BBOX)
        for i, cell in enumerate(self.cells):
            DisplacementVelocity.objects.create(
                mesh_cell=cell, fiscal_year="2025", velocity_cm_per_year=-0.05 * i
            )
            RoadExposure.objects.create(mesh_cell=cell, road_length_m=100.0 * (i + 1))

        elements = []
        for i, cell in enumerate(self.cells):
            lon, lat = cell.centroid.x, cell.centroid.y
            elements.append(
                {
                    "id": 2000 + i,
                    "geometry": [
                        {"lon": lon - 0.0005, "lat": lat},
                        {"lon": lon + 0.0005, "lat": lat},
                    ],
                }
            )

        from triage.build import run as run_triage

        with patch("triage.pipes.fetch_roads", return_value=elements):
            self.triage_run = run_triage(seed=42)

    def test_pipes_are_badged_illustrative_and_method_unvalidated(self):
        response = self.client.get("/api/triage/pipes/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["features"]), 0)

        for feature in data["features"]:
            props = feature["properties"]
            self.assertTrue(props["illustrative"])
            self.assertFalse(props["method_validated"])
            self.assertIn(props["tier"], {"low", "medium", "high"})

        self.assertTrue(any("未検証" in text for text in data["disclaimers"]))

    def test_ranking_never_exposes_raw_score(self):
        response = self.client.get("/api/triage/ranking/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["exists"])
        self.assertGreater(len(data["ranking"]), 0)

        for row in data["ranking"]:
            self.assertFalse(set(row.keys()) & self.FORBIDDEN_KEYS)
            self.assertIn(row["tier"], {"low", "medium", "high"})

        self.assertFalse(data["metrics"]["method_validated"])
        self.assertIn("baseline_road_length_spearman_rho", data["metrics"])
        self.assertTrue(any("未検証" in text for text in data["disclaimers"]))

    def test_disclaimers_disclose_sign_interpretation_inconsistency(self):
        """Monitorは精度限界を理由にセル符号(沈下/隆起)を解釈しないと明言する一方、
        Triageのsubsidence_signalはその符号を優先度算出に用いている
        (triage/scoring.py:compute_priority_index)。この一貫しない扱いを
        隠さず免責文で自認していることを保証する(独立敵対的監査 重大-1)。
        """
        response = self.client.get("/api/triage/ranking/")
        data = response.json()
        self.assertTrue(
            any("符号" in text and "解釈しない" in text for text in data["disclaimers"])
        )

    def test_ranking_order_is_tier_then_mesh_code_not_priority_index(self):
        """並び順がpriority_index降順ではなく、tier(高→中→低)→mesh_code昇順である
        ことを検証する(guardrail (b)の実装漏れの回帰防止)。

        既存のrun_triage生成フィクスチャは、たまたまmesh_codeの文字列順と
        priority_index降順が一致してしまう(座標が負値のため、mesh_codeの文字列
        比較順と数値順が逆転し、結果的にpriority_index降順と揃う)ため、両者が
        意図的に食い違う専用のMeshPriorityを直接構築して検証する。
        """
        from api.views import TIER_RANKING_ORDER

        distinct_mesh_codes = sorted({c.mesh_code for c in self.cells})[:4]
        self.assertGreaterEqual(len(distinct_mesh_codes), 4)

        isolated_run = TriageRun.objects.create(seed=1)
        # 全て同一tierにし、mesh_code昇順とpriority_index降順が正反対になるよう
        # 構築する: mesh_codeが最も若いセルにpriority_indexの最大値を与える。
        for rank, mesh_code in enumerate(distinct_mesh_codes):
            cell = next(c for c in self.cells if c.mesh_code == mesh_code)
            MeshPriority.objects.create(
                mesh_cell=cell,
                run=isolated_run,
                priority_index=float(len(distinct_mesh_codes) - rank),
                tier="high",
                velocity_cm_per_year=None,
                road_length_m=None,
                sewer_event_count=0,
                pipe_count=0,
            )

        response = self.client.get("/api/triage/ranking/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["run_id"], isolated_run.pk)
        actual_mesh_codes = [row["mesh_code"] for row in data["ranking"]]

        self.assertEqual(actual_mesh_codes, distinct_mesh_codes)
        self.assertNotEqual(actual_mesh_codes, list(reversed(distinct_mesh_codes)))
