"""250mメッシュ（JGD2011 / 平面直角座標系IX系 EPSG:6677 に基づく等面積グリッド）の
生成・参照ユーティリティ。全ての取込パイプライン(ingest/*)はここを通してMeshCellへ
値を紐づける。

対象エリアが関東地方以外に広がる場合はPROJECTED_SRIDを見直すこと（系IX=6677は
東京都・埼玉県・千葉県・神奈川県・茨城県・栃木県・群馬県・福島県が対象）。
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.gis.geos import Polygon

from .models import MeshCell

PROJECTED_SRID = 6677  # JGD2011 / Japan Plane Rectangular CS IX（関東域）
STORAGE_SRID = settings.SINKSCOPE_STORAGE_SRID
MESH_SIZE_M = 250


def _mesh_code(ix: int, iy: int) -> str:
    return f"250m-{ix}-{iy}"


def mesh_indices_for_point(x: float, y: float) -> tuple[int, int]:
    """投影座標(x, y)[m]が属するメッシュの格子インデックスを返す。"""
    return int(x // MESH_SIZE_M), int(y // MESH_SIZE_M)


def _mesh_cell_polygon(ix: int, iy: int) -> Polygon:
    """格子インデックスから、投影座標系(PROJECTED_SRID)でのメッシュ境界ポリゴンを作る。"""
    xmin, ymin = ix * MESH_SIZE_M, iy * MESH_SIZE_M
    xmax, ymax = xmin + MESH_SIZE_M, ymin + MESH_SIZE_M
    polygon = Polygon(((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)))
    polygon.srid = PROJECTED_SRID
    return polygon


def ensure_mesh_cells(bbox_geographic: tuple[float, float, float, float]) -> list[MeshCell]:
    """bbox_geographic=(west, south, east, north)[STORAGE_SRIDの経度緯度]を覆う
    250mメッシュのMeshCellを作成済みにし、範囲内の全MeshCellを返す（冪等）。
    """
    west, south, east, north = bbox_geographic
    bbox_polygon = Polygon.from_bbox((west, south, east, north))
    bbox_polygon.srid = STORAGE_SRID
    bbox_polygon.transform(PROJECTED_SRID)
    proj_xmin, proj_ymin, proj_xmax, proj_ymax = bbox_polygon.extent

    ix_min, iy_min = mesh_indices_for_point(proj_xmin, proj_ymin)
    ix_max, iy_max = mesh_indices_for_point(proj_xmax, proj_ymax)

    cells = []
    for ix in range(ix_min, ix_max + 1):
        for iy in range(iy_min, iy_max + 1):
            polygon = _mesh_cell_polygon(ix, iy)
            polygon.transform(STORAGE_SRID)
            cell, _ = MeshCell.objects.get_or_create(
                mesh_code=_mesh_code(ix, iy),
                defaults={"geom": polygon, "centroid": polygon.centroid},
            )
            cells.append(cell)
    return cells


def mesh_cell_for_geometry(geom) -> MeshCell | None:
    """任意の実座標(geomはSTORAGE_SRIDのPoint等)が属するMeshCellを返す。
    未生成のセルの場合はNone（先にensure_mesh_cellsでエリアを生成しておく前提）。
    """
    projected = geom.transform(PROJECTED_SRID, clone=True)
    ix, iy = mesh_indices_for_point(projected.x, projected.y)
    return MeshCell.objects.filter(mesh_code=_mesh_code(ix, iy)).first()
