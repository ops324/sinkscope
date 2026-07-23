"""デモ用に、コミット済みgolden snapshotからDBを投入する（オフライン・外部取得なし）。

`docker compose up` 後のDBは空で、地図に実データを出すには通常
`ingest_all`→`build_monitor`→`generate_triage` を手動実行する必要があり、しかも
各ingestは日本政府の生きたエンドポイントへ実HTTP取得する（遅く・不安定・ネット必須）。
読み手やデモ視聴者にこの手順を踏ませるのは非現実的である。

本コマンドは、再現ハーネス（reproduce_assessment）と同じ入力データ一式
（backend/analysis/fixtures/golden_snapshot.json.gz、来歴は docs/SNAPSHOT.md）を
`loaddata` し、同じ seed=42 で build_monitor → generate_triage を実行して、
**外部ネットに一切触れずに** 実データ相当の画面を出せる状態を作る。

reproduce_assessment との違い：あちらは「クリーンDBで再実行し数値を照合する検証」
であり既存データがあるとエラーにする。本コマンドは「デモ環境のセットアップ」なので、
既に投入済みなら冪等に skip し（--force で再投入）、数値の照合はしない
（照合は reproduce_assessment / CI の reproduce ジョブの仕事）。

表示される数値（片側p=0.9616, Moran's I=0.797, 道路長との順位相関 ρ=0.903）は、
reproduce ジョブが継続検証している値と同一であり、"見栄え用の別データ" を作らない。
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

from analysis.models import AnalysisRun
from triage.models import TriageRun

SNAPSHOT_FIXTURE_LABEL = "golden_snapshot"


class Command(BaseCommand):
    help = (
        "golden snapshot からデモ用DBをオフライン投入する"
        "（loaddata → build_monitor → generate_triage、seed=42、外部取得なし）。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="既にデモデータが投入済みでも、スナップショットを再読込して再構築する。",
        )

    def handle(self, *args, **options):
        force = options["force"]
        already_seeded = AnalysisRun.objects.exists() and TriageRun.objects.exists()
        if already_seeded and not force:
            self.stdout.write(
                self.style.WARNING(
                    "既にデモデータが投入済みです（AnalysisRun/TriageRunが存在）。"
                    "再投入するには --force を付けてください。何もせず終了します。"
                )
            )
            return

        self.stdout.write(f"--- loaddata {SNAPSHOT_FIXTURE_LABEL} ---")
        # fixtureは固定PK付きのため、再実行しても同一行を上書きするだけで冪等。
        call_command("loaddata", SNAPSHOT_FIXTURE_LABEL)

        self.stdout.write("--- build_monitor --seed 42 ---")
        call_command("build_monitor", seed=42)

        self.stdout.write("--- generate_triage --seed 42 ---")
        call_command("generate_triage", seed=42)

        analysis_run = AnalysisRun.objects.latest("created_at")
        triage_run = TriageRun.objects.latest("created_at")
        self.stdout.write(
            self.style.SUCCESS(
                "デモデータの投入が完了しました（外部ネット非依存）。"
                f" AnalysisRun #{analysis_run.pk} / TriageRun #{triage_run.pk}。"
            )
        )
        self.stdout.write(
            "表示される数値は docs/ASSESSMENT.md 記載の実測値と同一"
            "（reproduce ジョブが継続検証）。フロントは別途起動してください。"
        )
