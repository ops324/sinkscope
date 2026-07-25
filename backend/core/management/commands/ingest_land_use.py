from django.core.management.base import BaseCommand

from ingest.kokudo_suuchi import ingest_land_use


class Command(BaseCommand):
    help = "国土数値情報(KSJ)土地利用細分メッシュを取込み、MeshCellごとにGroundClassへ保存する。"

    def handle(self, *args, **options):
        count = ingest_land_use()
        self.stdout.write(self.style.SUCCESS(f"{count}件のメッシュにGroundClass.land_use_classを保存しました。"))
