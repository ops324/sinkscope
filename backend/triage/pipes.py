"""疑似管路(Illustrative)の決定的生成。

実際の管路台帳が存在しないため(商用化ロードマップ「実管路台帳」参照)、
ingest/osm_roads.py が取得するOSM道路網のセンターラインをそのまま「仮想パイプ」の
幾何として再利用する(README「疑似管路データは道路網上へ合成配置」)。

布設年・管種はseed固定のPython標準random(疑似乱数)で決定的に生成する架空値であり、
実在の管路台帳の代わりにはならない。同じseedなら常に同じ結果になることをテストで
保証する(再現性。docs/SPEC.md誠実性フレームワーク参照)。

Overpass APIへのネットワーク呼び出しは高コストなため、既にSyntheticPipeが存在する
場合は`--regenerate-pipes`を明示しない限り再取得しない(build.py参照)。
"""
from __future__ import annotations

import random

from django.contrib.gis.geos import LineString

from core.aoi import DEMO_AOI_BBOX
from core.mesh import STORAGE_SRID, ensure_mesh_cells, mesh_cell_for_geometry
from ingest.osm_roads import fetch_roads

from .models import PIPE_MATERIAL_CHOICES, SyntheticPipe

PIPE_MATERIALS = [code for code, _label in PIPE_MATERIAL_CHOICES]
INSTALL_YEAR_MIN = 1965
INSTALL_YEAR_MAX = 2015


def generate_synthetic_pipes(
    bbox: tuple[float, float, float, float] = DEMO_AOI_BBOX, seed: int = 42
) -> int:
    """道路網から疑似管路を決定的に生成し、SyntheticPipeへ保存する(既存分は洗い替え)。

    パイプの幾何 = 道路センターラインそのもの。含有メッシュはセンターラインの
    重心が落ちるMeshCellとする(mesh_cell_for_geometryはPointを期待するため)。
    AOI外のメッシュに落ちる場合(含有メッシュ未生成)はスキップする。
    """
    ensure_mesh_cells(bbox)
    elements = fetch_roads(bbox)
    rng = random.Random(seed)

    SyntheticPipe.objects.filter(seed=seed).delete()

    created = 0
    for element in elements:
        coords = element.get("geometry")
        if not coords or len(coords) < 2:
            continue

        line = LineString([(pt["lon"], pt["lat"]) for pt in coords], srid=STORAGE_SRID)
        cell = mesh_cell_for_geometry(line.centroid)
        if cell is None:
            continue

        SyntheticPipe.objects.create(
            mesh_cell=cell,
            geom=line,
            osm_way_id=element.get("id"),
            seed=seed,
            install_year=rng.randint(INSTALL_YEAR_MIN, INSTALL_YEAR_MAX),
            pipe_material=rng.choice(PIPE_MATERIALS),
        )
        created += 1

    return created
