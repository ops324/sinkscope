from django.core.management.base import BaseCommand

from core.aoi import DEMO_AOI_BBOX
from core.mesh import ensure_mesh_cells


class Command(BaseCommand):
    help = "対象エリア(DEMO_AOI_BBOX)を覆う250mメッシュのMeshCellを生成する。"

    def handle(self, *args, **options):
        cells = ensure_mesh_cells(DEMO_AOI_BBOX)
        self.stdout.write(self.style.SUCCESS(f"{len(cells)}件のMeshCellを用意しました。"))
