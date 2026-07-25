from django.core.management.base import BaseCommand

from ingest.kanbotsu_xlsx import ingest_subsidence_events


class Command(BaseCommand):
    help = "国土交通省 道路陥没オープンデータ(令和5・6年度)を取込み、地名をジオコーディングする。"

    def handle(self, *args, **options):
        count = ingest_subsidence_events()
        self.stdout.write(self.style.SUCCESS(f"{count}件のSubsidenceEventを保存しました。"))
