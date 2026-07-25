from django.core.management.base import BaseCommand

from ingest.dem import ingest_elevation


class Command(BaseCommand):
    help = "国土地理院 標高タイルからメッシュ中心点の標高を取込み、GroundClassへ保存する。"

    def handle(self, *args, **options):
        count = ingest_elevation()
        self.stdout.write(self.style.SUCCESS(f"{count}件のメッシュにGroundClass.elevation_mを保存しました。"))
