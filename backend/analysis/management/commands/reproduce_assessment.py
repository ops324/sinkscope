"""docs/ASSESSMENT.md §2 の実測値を、コミット済みgolden snapshotから再現し照合する。

背景: build_monitor/generate_triageの出力(p値・Moran's I・道路長との順位相関ρ等)
は、これまでdocs/ASSESSMENT.mdに文書化されているだけで、第三者が「本当にそうなる
のか」を自分の手で確かめる手段が無かった。生データ(data/raw/*)は.gitignoreされ、
GSI/OSM等のライブソースは時間とともにdriftするため、この文書化された数値は実質
再現不能だった。

本コマンドは、実際にASSESSMENT.mdの数値の直接の裏付けとなったAnalysisRun #4 /
TriageRun #2の入力データ一式(backend/analysis/fixtures/golden_snapshot.json.gz。
docs/SNAPSHOT.md参照)をクリーンなDBへ読み込み、同じseed=42でbuild_monitor →
generate_triageを再実行し、得られたmetrics_jsonがgolden_snapshot_expected_metrics.json
(単一情報源)の値と一致するかを機械的に照合する。
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from analysis.models import AnalysisRun
from triage.models import TriageRun

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"
SNAPSHOT_FIXTURE_LABEL = "golden_snapshot"
EXPECTED_METRICS_PATH = FIXTURES_DIR / "golden_snapshot_expected_metrics.json"

# 環境差(BLASバックエンド等)による浮動小数点の最下位ビットのブレを許容するための
# 許容誤差。golden_snapshotの入力とseedが同一である限り、アルゴリズム自体は
# 決定論的なので、これより大きくずれた場合は真の再現失敗(drift)とみなす。
FLOAT_TOLERANCE = 1e-6


def _flatten(prefix: str, value):
    """ネストしたdictを"a.b.c"形式のフラットな(key, value)列に展開する。"""
    if isinstance(value, dict):
        for key, sub_value in value.items():
            yield from _flatten(f"{prefix}.{key}" if prefix else key, sub_value)
    else:
        yield prefix, value


def _mismatches(expected: dict, actual: dict) -> list[tuple[str, object, object]]:
    results = []
    for key, expected_value in _flatten("", expected):
        actual_value = actual
        for part in key.split("."):
            actual_value = actual_value.get(part) if isinstance(actual_value, dict) else None
        if isinstance(expected_value, float):
            if actual_value is None or abs(actual_value - expected_value) > FLOAT_TOLERANCE:
                results.append((key, expected_value, actual_value))
        elif actual_value != expected_value:
            results.append((key, expected_value, actual_value))
    return results


class Command(BaseCommand):
    help = (
        "golden snapshotからdocs/ASSESSMENT.mdの数値(p値・Moran's I・ρ等)を再現し、"
        "golden_snapshot_expected_metrics.jsonの値と照合する。クリーンなDB(既存の"
        "AnalysisRun/TriageRunが無い状態)での実行を前提とする。"
    )

    def handle(self, *args, **options):
        if AnalysisRun.objects.exists() or TriageRun.objects.exists():
            raise CommandError(
                "既存のAnalysisRun/TriageRunが見つかりました。本コマンドはクリーンな"
                "DBでの実行を前提とします(scripts/reproduce.shは専用の使い捨て"
                "Compose環境を使うことでこれを保証しています)。開発用DBを直接指して"
                "いないか確認してください。"
            )

        self.stdout.write(f"--- loaddata {SNAPSHOT_FIXTURE_LABEL} ---")
        call_command("loaddata", SNAPSHOT_FIXTURE_LABEL)

        self.stdout.write("--- build_monitor --seed 42 ---")
        call_command("build_monitor", seed=42)

        self.stdout.write("--- generate_triage --seed 42 ---")
        call_command("generate_triage", seed=42)

        analysis_run = AnalysisRun.objects.latest("created_at")
        triage_run = TriageRun.objects.latest("created_at")

        expected = json.loads(EXPECTED_METRICS_PATH.read_text(encoding="utf-8"))
        actual = {
            "analysis": {
                "in_aoi_event_count": analysis_run.metrics_json.get("in_aoi_event_count"),
                "in_aoi_sewer_event_count": analysis_run.metrics_json.get(
                    "in_aoi_sewer_event_count"
                ),
                "permutation_test": analysis_run.metrics_json.get("permutation_test", {}),
            },
            "triage": {
                "pipe_count": triage_run.metrics_json.get("pipe_count"),
                "baseline_road_length_spearman_rho": triage_run.metrics_json.get(
                    "baseline_road_length_spearman_rho"
                ),
            },
        }

        mismatches = _mismatches(
            {"analysis": expected["analysis"], "triage": expected["triage"]}, actual
        )

        if mismatches:
            self.stdout.write(self.style.ERROR("再現に失敗しました(drift検知):"))
            for key, expected_value, actual_value in mismatches:
                self.stdout.write(f"  {key}: expected={expected_value!r} actual={actual_value!r}")
            raise CommandError(
                f"{len(mismatches)}件の指標が docs/ASSESSMENT.md の記載値(golden_"
                "snapshot_expected_metrics.json)と一致しませんでした。"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"再現成功: AnalysisRun #{analysis_run.pk} / TriageRun #{triage_run.pk} の"
                "全指標がdocs/ASSESSMENT.mdの記載値と一致しました。"
            )
        )
        for key, value in _flatten("", actual):
            self.stdout.write(f"  {key} = {value}")
