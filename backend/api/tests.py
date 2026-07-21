"""api アプリのテスト(Django標準TestCase)。

誠実性フレームワークが要求する2点を確認する:
  1. /api/events/ がAOI外(mesh_cellが紐づかない)イベントを返さないこと
  2. /api/mesh/summary/ が「ハザードスコア」的なフィールドを一切含まず、
     実データの集約のみを返すこと(docs/SPEC.md §7参照)
"""
from django.contrib.gis.geos import Point
from django.test import TestCase

from analysis.models import AnalysisRun, MeshSummary
from core.mesh import ensure_mesh_cells
from core.models import DisplacementVelocity, SubsidenceEvent

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
