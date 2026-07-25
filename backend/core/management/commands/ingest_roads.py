from django.core.management.base import BaseCommand

from ingest.osm_roads import ingest_roads


class Command(BaseCommand):
    help = "OpenStreetMapの道路網からメッシュ単位の道路延長(曝露)を取り込む。"

    def handle(self, *args, **options):
        count = ingest_roads()
        self.stdout.write(self.style.SUCCESS(f"{count}件のメッシュにRoadExposureを保存しました。"))
