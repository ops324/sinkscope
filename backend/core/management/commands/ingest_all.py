from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Monitorモジュールの実データ取込を正しい順序で一括実行する(1エリアでのE2E検証用)。"

    def handle(self, *args, **options):
        steps = [
            "generate_mesh",
            "ingest_displacement",
            "ingest_land_use",
            "ingest_elevation",
            "ingest_roads",
            "ingest_subsidence",
        ]
        for step in steps:
            self.stdout.write(f"--- {step} ---")
            call_command(step)
        self.stdout.write(self.style.SUCCESS("Monitorデータ取込が完了しました。"))
