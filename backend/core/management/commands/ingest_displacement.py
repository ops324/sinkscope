from django.core.management.base import BaseCommand

from ingest.gsi_displacement import ingest_displacement_velocity


class Command(BaseCommand):
    help = "国土地理院 衛星SAR地盤変動測量成果(準上下方向変位速度)を取込み、DisplacementVelocityへ保存する。"

    def handle(self, *args, **options):
        count = ingest_displacement_velocity()
        self.stdout.write(self.style.SUCCESS(f"{count}件のメッシュにDisplacementVelocityを保存しました。"))
