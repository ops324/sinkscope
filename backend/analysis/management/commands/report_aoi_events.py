from django.core.management.base import BaseCommand

from analysis.groundtruth import count_aoi_events


class Command(BaseCommand):
    help = (
        "AOI内の道路陥没イベント数を実測する。SPEC§4.5の「933件/341件」は東京都・埼玉県"
        "全体の数字であり、AOI内の実数はこれとは別に数える必要がある。この実測値で"
        "build_monitor が付録の空間パーミュテーション検定を実施するか（下水道原因n>=10）、"
        "純粋な記述に留めるかを判断する。"
    )

    def handle(self, *args, **options):
        summary = count_aoi_events()

        self.stdout.write(f"AOI内 陥没イベント総数: {summary['in_aoi_event_count']}")
        self.stdout.write(f"  うち下水道原因: {summary['in_aoi_sewer_event_count']}")
        self.stdout.write(f"AOI内 占有字数（重心座標ベース）: {summary['occupied_oaza_count']}")
        self.stdout.write(
            f"  うち下水道原因が占める字数: {summary['occupied_oaza_sewer_count']}"
        )

        min_n = summary["permutation_test_min_n"]
        sewer_n = summary["in_aoi_sewer_event_count"]
        if summary["permutation_test_eligible"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"下水道原因イベント数({sewer_n}) >= {min_n} のため、"
                    "付録の空間パーミュテーション検定を実施します。"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"下水道原因イベント数({sewer_n}) < {min_n} のため、"
                    "付録の空間パーミュテーション検定はスキップします"
                    "（統計検定は行わず、視覚的な重ね合わせと正直なn開示のみ提示します）。"
                )
            )
