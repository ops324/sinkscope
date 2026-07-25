"""APIレスポンスを静的JSONへ焼き固める（シェア用の静的サイト配信、D7）。

デモデータは golden snapshot で固定（いつ見ても同じ）なので、api/views.py の各
エンドポイントが返すJSONをあらかじめファイルへ書き出しておけば、フロントは
サーバ・DBに一切アクセスせず、コミット済みJSONだけで動く完全静的サイトになる。
生成物は frontend/public/data/ に置き、Viteが dist/ 直下へコピーする（GitHub Pages等へ）。

重要な設計:
- **本物のview関数を RequestFactory 経由で呼び、response.content をそのまま書く**。
  独自のシリアライズを書かないため、ライブAPIとバイト等価になり "見栄え用の別データ" を
  作らない（誠実性フレームワーク／docs/SPEC.md §5 と同じ思想）。
- フロントが実際に呼ぶのはパラメータなしの5エンドポイントのみ（frontend/src/api/client.ts、
  fetchEvents は cause_facility 無しで呼ばれ絞り込みは画面側）。よって5ファイルで足りる。

--check（CIのズレ検出ガード）:
  コミット済みJSONと新規生成物を **意味的に** 比較する。AnalysisRun.created_at は
  auto_now_add で、seed_demo は build_monitor/generate_triage を毎回新規実行して新しい
  pk・時刻の run を作るため、created_at / run_id / run.id は seed のたびに変わる。これらは
  検証対象データ（変位速度・土地利用・標高・道路延長・イベント・tier・metrics・geometry・
  disclaimers）ではなく来歴ノイズなので、比較前に allowlist で除外する。substance は
  seed=42＋固定snapshot で決定的（再現ハーネスが継続検証）なので、除外後は一致するはず。
  これで「元データを変えたのにコミット済みJSONを更新し忘れた」ズレは検出しつつ、時刻/pk
  差だけで毎回失敗することを避ける。
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from api import views

# (出力ファイル名, view関数, ダミーのGETパス)
ENDPOINTS = [
    ("mesh-summary.json", views.mesh_summary, "/api/mesh/summary/"),
    ("events.json", views.events, "/api/events/"),
    ("analysis-run-latest.json", views.analysis_run_latest, "/api/analysis/run/latest/"),
    ("triage-pipes.json", views.triage_pipes, "/api/triage/pipes/"),
    ("triage-ranking.json", views.triage_ranking, "/api/triage/ranking/"),
]

# 意味的比較（--check）で無視する、実行ごとに揺れる来歴フィールド。
# top-levelの created_at / run_id と、run オブジェクト内の id / created_at のみ。
VOLATILE_TOP_LEVEL_KEYS = ("created_at", "run_id")
VOLATILE_RUN_KEYS = ("id", "created_at")


def _strip_volatile(payload):
    """比較用に、揺れる来歴キー（時刻・pk）だけを除いたコピーを返す。"""
    if not isinstance(payload, dict):
        return payload
    cleaned = {k: v for k, v in payload.items() if k not in VOLATILE_TOP_LEVEL_KEYS}
    run = cleaned.get("run")
    if isinstance(run, dict):
        cleaned["run"] = {k: v for k, v in run.items() if k not in VOLATILE_RUN_KEYS}
    return cleaned


class Command(BaseCommand):
    help = (
        "api/views.py の5エンドポイントのレスポンスを静的JSONへ書き出す"
        "（シェア用静的サイト用）。--check でコミット済みJSONとの意味的一致を検証。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            required=True,
            help="JSONの出力先ディレクトリ（存在しなければ作成）。",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help=(
                "書き出さず、--out 内の既存JSONと新規生成物を意味的に比較する"
                "（揺れる created_at/run_id/run.id を除外）。差異があれば非0終了。"
            ),
        )

    def handle(self, *args, **options):
        out_dir = Path(options["out"])
        check = options["check"]

        request_factory = RequestFactory()
        mismatches: list[str] = []

        if not check:
            out_dir.mkdir(parents=True, exist_ok=True)

        for filename, view, path in ENDPOINTS:
            response = view(request_factory.get(path))
            content = response.content
            target = out_dir / filename

            if check:
                if not target.exists():
                    mismatches.append(f"{filename}: コミット済みファイルが存在しません")
                    continue
                committed = _strip_volatile(json.loads(target.read_bytes()))
                fresh = _strip_volatile(json.loads(content))
                if committed != fresh:
                    mismatches.append(
                        f"{filename}: コミット済みJSONが再生成結果と一致しません"
                        "（元データ変更後に make static で再生成し忘れていませんか）"
                    )
                else:
                    self.stdout.write(f"OK  {filename}")
            else:
                target.write_bytes(content)
                self.stdout.write(f"wrote {filename} ({len(content):,} bytes)")

        if check and mismatches:
            raise CommandError(
                "静的JSONのズレを検出しました:\n  - " + "\n  - ".join(mismatches)
            )

        if check:
            self.stdout.write(
                self.style.SUCCESS("静的JSONはコミット済みと意味的に一致しています。")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"{len(ENDPOINTS)}個のJSONを {out_dir} に書き出しました。")
            )
