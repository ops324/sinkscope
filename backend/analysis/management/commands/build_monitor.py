from django.core.management.base import BaseCommand

from analysis.build import run


class Command(BaseCommand):
    help = (
        "Monitorレイヤーを構築する：実データの集約(MeshSummary)と、n次第の付録空間"
        "パーミュテーション検定を実行し、結果をAnalysisRunに記録する。"
        "回帰・分類モデルの学習やハザードスコアの算出は行わない（docs/SPEC.md §7参照）。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fiscal-year",
            default=None,
            help="対象年度(省略時は取込済みDisplacementVelocityの最新年度)",
        )
        parser.add_argument("--seed", type=int, default=42, help="パーミュテーション検定の乱数シード")

    def handle(self, *args, **options):
        run_obj = run(fiscal_year=options["fiscal_year"], seed=options["seed"])
        metrics = run_obj.metrics_json

        self.stdout.write(self.style.SUCCESS(f"AnalysisRun #{run_obj.pk} を作成しました。"))
        self.stdout.write(f"対象年度: {run_obj.fiscal_year or '(未取込)'}")
        self.stdout.write(f"MeshSummary: {run_obj.mesh_summaries.count()}件")
        self.stdout.write(f"AOI内イベント総数: {metrics['in_aoi_event_count']}")
        self.stdout.write(f"AOI内下水道原因イベント数: {metrics['in_aoi_sewer_event_count']}")

        perm = metrics["permutation_test"]
        if perm.get("skipped"):
            self.stdout.write(self.style.WARNING(f"付録検定: スキップ（{perm['reason']}）"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"付録検定: 観測差={perm['observed_mean_diff_cm_per_year']:.4f} cm/年, "
                    f"片側p値={perm['p_value_one_sided']:.4f}, 両側p値={perm['p_value_two_sided']:.4f} "
                    f"(k={perm['k_sewer_cells']}, underpowered={perm['underpowered']})"
                )
            )
