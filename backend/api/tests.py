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
"""
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TestCase

from analysis.models import AnalysisRun, MeshSummary
from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity, RoadExposure, SubsidenceEvent

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
