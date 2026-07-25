from django.core.management.base import BaseCommand

from triage.build import run


class Command(BaseCommand):
    help = (
        "Triageレイヤーを構築する：疑似管路(Illustrative)の合成配置と、Monitorの"
        "実データに基づく点検優先度tierの算出を行い、結果をTriageRunに記録する。"
        "回帰・分類モデルの学習は行わず、本プロジェクトの統計検定はこの手法を"
        "検証していない(docs/SPEC.md §7参照)。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42, help="疑似管路生成・再現性の乱数シード")
        parser.add_argument(
            "--regenerate-pipes",
            action="store_true",
            help="既存の疑似管路を破棄し、Overpass APIから再取得して作り直す",
        )

    def handle(self, *args, **options):
        run_obj = run(seed=options["seed"], regenerate_pipes=options["regenerate_pipes"])
        metrics = run_obj.metrics_json

        self.stdout.write(self.style.SUCCESS(f"TriageRun #{run_obj.pk} を作成しました。"))
        self.stdout.write(f"疑似管路数(Illustrative): {metrics['pipe_count']}")
        self.stdout.write(f"優先度算出対象メッシュ数: {metrics['eligible_mesh_count']}")
        rho = metrics["baseline_road_length_spearman_rho"]
        self.stdout.write(f"道路長ベースラインとのSpearman順位相関: {rho}")
        self.stdout.write(
            self.style.WARNING(
                "手法は未検証(method_validated=False)。本プロジェクトの統計検定は"
                "この優先度の背景仮説を支持していない。"
            )
        )
