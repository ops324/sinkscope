"""陥没イベントを「字（＝ジオコード重心座標）」単位の面として扱うヘルパ。

ingest/kanbotsu_xlsx.py のジオコーディングは字・大字レベルの精度で、同一字内の
複数件は同一座標にスナップされる（docs/SPEC.md §4.5）。これを点の精度と偽らず、
イベント集計・地図表示・付録検定のすべてで「重心座標でグルーピングした字単位」の
面として一貫して扱う。

PERMUTATION_TEST_MIN_N は、下水道原因イベントが何件以上あれば付録の空間パーミュ
テーション検定（analysis/permutation.py）を実施するかのしきい値。これ未満なら検定
自体を実施せず、AOI内イベント数を正直に開示したうえで純粋な記述に留める
（docs/SPEC.md §7の確定判断）。
"""
from __future__ import annotations

from collections import defaultdict

from core.models import SubsidenceEvent

SEWER_CAUSE_KEYWORD = "下水道"
PERMUTATION_TEST_MIN_N = 10


def in_aoi_events(cause_facility_contains: str | None = None):
    """AOI内（mesh_cellが紐づいている＝生成済みメッシュ内に収まっている）イベントのqueryset。

    mesh_cellがNoneのイベントは、ジオコード座標が対象AOI外に落ちたもの（東京都・埼玉県の
    他エリア）であり、本プロジェクトの対象範囲外として除外する。
    """
    qs = SubsidenceEvent.objects.filter(mesh_cell__isnull=False, geom__isnull=False)
    if cause_facility_contains:
        qs = qs.filter(cause_facility__icontains=cause_facility_contains)
    return qs.select_related("mesh_cell")


def _oaza_key(event: SubsidenceEvent) -> tuple[float, float]:
    """同一字は同一座標にスナップされる前提で、重心座標を字の代理キーとする。"""
    return (round(event.geom.x, 6), round(event.geom.y, 6))


def distinct_oaza_count(events) -> int:
    return len({_oaza_key(e) for e in events})


def group_by_oaza(events) -> dict[tuple[float, float], list[SubsidenceEvent]]:
    """イベント列を字（重心座標）単位でグルーピングする。"""
    grouped: dict[tuple[float, float], list[SubsidenceEvent]] = defaultdict(list)
    for event in events:
        grouped[_oaza_key(event)].append(event)
    return grouped


def count_aoi_events() -> dict:
    """AOI内イベントのn実測サマリ。

    report_aoi_events コマンドと build_monitor コマンドの両方から呼ばれる、
    このプロジェクトにおける「nの唯一の真実源」。
    """
    all_events = list(in_aoi_events())
    sewer_events = [e for e in all_events if SEWER_CAUSE_KEYWORD in (e.cause_facility or "")]

    return {
        "in_aoi_event_count": len(all_events),
        "in_aoi_sewer_event_count": len(sewer_events),
        "occupied_oaza_count": distinct_oaza_count(all_events),
        "occupied_oaza_sewer_count": distinct_oaza_count(sewer_events),
        "permutation_test_min_n": PERMUTATION_TEST_MIN_N,
        "permutation_test_eligible": len(sewer_events) >= PERMUTATION_TEST_MIN_N,
    }
