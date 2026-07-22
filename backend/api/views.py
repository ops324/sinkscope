"""SinkScope API views.

すべての地物レスポンスは、保存用座標系(SINKSCOPE_STORAGE_SRID=6668, JGD2011)から
Web地図の慣例であるWGS84(EPSG:4326)へPostGIS側で変換して返す(Transform+AsGeoJSON)。

mesh_summary / events は「実データの集約」「実陥没イベント」をそのまま返すだけで、
ハザードスコアや期待陥没率のような予測・推論結果は一切含まない
(docs/SPEC.md §7の確定判断)。推論結果を返すのは analysis_run_latest のみで、
これも「AOI内の実イベント数」「(実施していれば)付録検定の結果」「限界の明示」を
セットで返す。

triage_pipes / triage_ranking は Triage(意思決定支援層)のIllustrativeなレスポンス。
連続の priority_index は一切返さず、tier(高/中/低)のみを公開する
(独立敵対的監査 guardrail (b))。TRIAGE_DISCLAIMERS は「疑似パイプというデータ」
だけでなく「優先度算出という手法」自体が未検証であることも明示する
(guardrail (a))。
"""
import json

from django.contrib.gis.db.models.functions import AsGeoJSON, Transform
from django.http import JsonResponse

from analysis.models import AnalysisRun, MeshSummary
from core.models import SubsidenceEvent
from triage.models import MeshPriority, SyntheticPipe, TriageRun

WEB_SRID = 4326

DISCLAIMERS = [
    "これは予測ではなく、実データの統合と、実陥没に対する視覚的・(可能な場合は)"
    "統計的な答え合わせです。",
    "面的なトリアージであり、個々の管路・マンホールなど資産単位の予測ではありません。",
    "InSARは局所的な空洞や突発的な陥没の予兆検知には向いていません。",
    "GSI年度速度の精度は概ね±数mm/年とされ、本AOI平均はその精度限界に近いため、"
    "セル単位の符号(沈下/隆起)は解釈していません。",
]

TRIAGE_DISCLAIMERS = [
    "疑似管路(Illustrative)は実在の管路台帳ではなく、道路網上へ合成配置した架空の"
    "データです。布設年・管種も架空値であり、実在の設備とは無関係です。",
    "この点検優先度ランキングの手法自体が未検証です。本プロジェクト自身の統計検定は"
    "「陥没(下水道原因)箇所は変位速度がより負に偏る」という仮説を支持しませんでした"
    "(片側p=0.962)。tierは検証済みの予測ではなく、事前のヒューリスティックです。",
    "面的なトリアージであり、個々の管路・マンホールなど資産単位の予測ではありません。",
    "本ランキングは点検ワークリストがどう見え・どう振る舞うかのUI実証であり、"
    "この地域が実際に高優先度であることを統計的に示すものではありません。",
]


def _fiscal_year_provenance(metrics_json: dict) -> str:
    """metrics_json["displacement_provenance"]から、年度ラベルの信頼度を1語で要約する。

    GSIの変位速度APIには年度を選択するパラメータが無く、`fiscal_year`は取得記録
    (DisplacementAcquisition)のbest-effortラベルに過ぎない(docs/SPEC.md §4.1)。
    APIがこの年度を無条件・断定的に返すと、来歴汚染バグ(F9)と同じ過ちを表示層で
    繰り返すことになるため、必ずこのフラグと併せて提示する。

    - "verified": 表示に使われた全acquisitionがfilename/operator_override由来。
    - "unverified": 1件でも取得時刻からの未検証推定(unverified_retrieval_time)が
      混在する。GSIの成果公開ラグにより、実際の成果年度と異なる可能性がある。
    - "unknown": acquisitionの記録が無い(acquisition未設定の旧データ、または未取込)。
    """
    provenance = (metrics_json or {}).get("displacement_provenance") or {}
    acquisitions = provenance.get("acquisitions") or []
    if not acquisitions:
        return "unknown"
    if all(
        a.get("fiscal_year_provenance") in ("filename", "operator_override")
        for a in acquisitions
    ):
        return "verified"
    return "unverified"


def health(request):
    return JsonResponse({"status": "ok", "service": "sinkscope-api"})


def mesh_summary(request):
    """最新AnalysisRunのMeshSummaryを、MeshCellポリゴン(4326)込みのGeoJSONで返す。

    ハザード色やスコアは含まない。フロントは変位速度・土地利用・標高・道路延長・
    観測イベント数という実データをそのまま切り替えて可視化する。
    """
    latest_run = AnalysisRun.objects.order_by("-created_at").first()
    if latest_run is None:
        return JsonResponse({"type": "FeatureCollection", "features": [], "run": None})

    summaries = (
        MeshSummary.objects.filter(run=latest_run)
        .select_related("mesh_cell")
        .annotate(geom_4326=AsGeoJSON(Transform("mesh_cell__geom", WEB_SRID)))
        .order_by("mesh_cell__mesh_code")
    )

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(summary.geom_4326),
            "properties": {
                "mesh_code": summary.mesh_cell.mesh_code,
                "velocity_cm_per_year": summary.velocity_cm_per_year,
                "land_use_class": summary.land_use_class,
                "elevation_m": summary.elevation_m,
                "road_length_m": summary.road_length_m,
                "event_count": summary.event_count,
                "sewer_event_count": summary.sewer_event_count,
            },
        }
        for summary in summaries
    ]

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "run": {
                "id": latest_run.pk,
                "fiscal_year": latest_run.fiscal_year,
                "fiscal_year_provenance": _fiscal_year_provenance(latest_run.metrics_json),
            },
            "features": features,
        }
    )


def events(request):
    """AOI内(mesh_cellが紐づいている)道路陥没イベントのみをGeoJSONで返す。

    AOI外のイベント(東京都・埼玉県の対象エリア外)は意図的に除外する。含めると
    「AOI内の実データ」という本APIの前提と矛盾するため。
    """
    queryset = SubsidenceEvent.objects.filter(mesh_cell__isnull=False, geom__isnull=False)

    cause_facility = request.GET.get("cause_facility")
    if cause_facility:
        queryset = queryset.filter(cause_facility__icontains=cause_facility)

    queryset = queryset.annotate(geom_4326=AsGeoJSON(Transform("geom", WEB_SRID))).order_by("id")

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(event.geom_4326),
            "properties": {
                "fiscal_year": event.fiscal_year,
                "prefecture": event.prefecture,
                "location_text": event.location_text,
                "road_name": event.road_name,
                "cause_facility": event.cause_facility,
                "road_jurisdiction": event.road_jurisdiction,
                "geocode_confidence": event.geocode_confidence,
            },
        }
        for event in queryset
    ]

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "note": (
                "位置は地名文字列からのジオコーディング(字・大字レベル)。"
                "同一字内の複数件は同一座標に重なって表示される。"
            ),
            "features": features,
        }
    )


def analysis_run_latest(request):
    """最新AnalysisRunのメトリクス(n実測値・付録検定の有無と結果)と免責文を返す。

    フロントのHonestyPanelはこのエンドポイントを直接描画に使う。
    """
    latest_run = AnalysisRun.objects.order_by("-created_at").first()
    if latest_run is None:
        return JsonResponse({"exists": False, "disclaimers": DISCLAIMERS})

    return JsonResponse(
        {
            "exists": True,
            "run_id": latest_run.pk,
            "created_at": latest_run.created_at.isoformat(),
            "fiscal_year": latest_run.fiscal_year,
            "fiscal_year_provenance": _fiscal_year_provenance(latest_run.metrics_json),
            "metrics": latest_run.metrics_json,
            "disclaimers": DISCLAIMERS,
        }
    )


def triage_pipes(request):
    """疑似管路(Illustrative)をLineString GeoJSONで返す。

    連続スコアは含まない。含まれるtierはMeshPriority(最新TriageRun)から継承した
    値で、パイプ自体に予測的な意味は一切ない(道路網上への合成配置に過ぎない)。
    """
    latest_run = TriageRun.objects.order_by("-created_at").first()
    if latest_run is None:
        return JsonResponse(
            {"type": "FeatureCollection", "features": [], "run": None, "disclaimers": TRIAGE_DISCLAIMERS}
        )

    tier_by_mesh = dict(
        MeshPriority.objects.filter(run=latest_run).values_list("mesh_cell_id", "tier")
    )

    pipes = (
        SyntheticPipe.objects.select_related("mesh_cell")
        .annotate(geom_4326=AsGeoJSON(Transform("geom", WEB_SRID)))
        .order_by("id")
    )

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(pipe.geom_4326),
            "properties": {
                "illustrative": True,
                "method_validated": False,
                "mesh_code": pipe.mesh_cell.mesh_code,
                "install_year": pipe.install_year,
                "pipe_material": pipe.pipe_material,
                "tier": tier_by_mesh.get(pipe.mesh_cell_id),
            },
        }
        for pipe in pipes
    ]

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "run": {"id": latest_run.pk, "created_at": latest_run.created_at.isoformat()},
            "features": features,
            "disclaimers": TRIAGE_DISCLAIMERS,
        }
    )


def triage_ranking(request):
    """メッシュ単位の点検優先度ランキングをtierと構成実測値の分解で返す。

    priority_index(内部の連続値)は一切返さない。road_length単独ベースラインとの
    Spearman順位相関(baseline_road_length_spearman_rho)を必ず含め、
    「結局ただの道路長地図では?」を利用者自身が判断できるようにする
    (docs/SPEC.md §7.1、独立敵対的監査 guardrail)。
    """
    latest_run = TriageRun.objects.order_by("-created_at").first()
    if latest_run is None:
        return JsonResponse(
            {"exists": False, "ranking": [], "disclaimers": TRIAGE_DISCLAIMERS}
        )

    priorities = (
        MeshPriority.objects.filter(run=latest_run)
        .select_related("mesh_cell")
        .order_by("-priority_index")
    )

    ranking = [
        {
            "mesh_code": p.mesh_cell.mesh_code,
            "tier": p.tier,
            "velocity_cm_per_year": p.velocity_cm_per_year,
            "road_length_m": p.road_length_m,
            "sewer_event_count": p.sewer_event_count,
            "pipe_count": p.pipe_count,
        }
        for p in priorities
    ]

    return JsonResponse(
        {
            "exists": True,
            "run_id": latest_run.pk,
            "created_at": latest_run.created_at.isoformat(),
            "seed": latest_run.seed,
            "weights": latest_run.params_json.get("weights"),
            "metrics": latest_run.metrics_json,
            "ranking": ranking,
            "disclaimers": TRIAGE_DISCLAIMERS,
        }
    )
