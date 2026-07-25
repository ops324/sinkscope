# Golden Snapshot（再現性ハーネスの入力データ来歴）

`docs/ASSESSMENT.md` §2 に記載した実測値（片側p値・Moran's I・道路長との
Spearman順位相関ρ）は、これまで文書化されているだけで、第三者が自分の手で
確かめる方法が無かった。生データ（`data/raw/*`）は`.gitignore`されており、
GSI/OSM等のライブソースは時間とともに内容が変わりうる（drift）ため、文書化
された数値は実質再現不能だった。

本ドキュメントが記録する `backend/analysis/fixtures/golden_snapshot.json.gz`
は、**実際に`docs/ASSESSMENT.md`の数値の直接の裏付けとなった入力データ一式**
（AnalysisRun #4 / TriageRun #2 が参照した状態のDB）をそのまま固定化したもの
である。`scripts/reproduce.sh` はこれをクリーンなDBへ読み込み、同じ
`seed=42`で`build_monitor`→`generate_triage`を再実行し、得られた
`metrics_json`が期待値と一致するかを機械的に照合する。

## 単一情報源

**期待値の正は `backend/analysis/fixtures/golden_snapshot_expected_metrics.json`
であり、このファイルとASSESSMENT.mdの数値が食い違う場合はexpected_metrics.json
を正とする。** 以前p値をdocstringに固定文字列として埋め込み、検定の再実行に
追随できなかった過ち（独立敵対的監査、`triage/scoring.py`参照）と同じ轍を
踏まないための方針である。

## 収録データと来歴

| モデル | 件数 | 内容 |
|---|---|---|
| `core.MeshCell` | 7,918 | DEMO_AOI_BBOX (139.75, 35.62, 139.95, 35.86) を覆う250mメッシュ |
| `core.DisplacementAcquisition` | 0 | 下記「既知の欠落」参照 |
| `core.DisplacementVelocity` | 7,918 | GSI衛星SAR変位速度（実データ） |
| `core.GroundClass` | 7,886 | KSJ土地利用細分メッシュ由来（実データ） |
| `core.RoadExposure` | 7,082 | OSM道路延長（実データ） |
| `core.SubsidenceEvent` | 934 | MLIT公表の道路陥没事案、ジオコーディング済み（実データ） |
| `triage.SyntheticPipe` | 51,084 | OSM道路網に合成配置した疑似管路（**Illustrative**。布設年・管種は`seed=42`の疑似乱数による架空値） |

`analysis.AnalysisRun` / `analysis.MeshSummary` / `triage.TriageRun` /
`triage.MeshPriority`（計算結果）は**意図的に含めない**。これらを含めてしまうと
「計算せず結果を読むだけ」になり、再現性の検証にならないため、
`reproduce_assessment`コマンドが毎回ゼロから計算し直す。

### 既知の欠落（隠さず開示）

`DisplacementVelocity`が7,918件あるのに対し、`DisplacementAcquisition`
（取得来歴の監査記録、`content_sha256`によるヴィンテージ識別。PR #5参照）は
**0件**である。これは今回の変更が生んだものではなく、来歴トラッキング機能
（`ingest/gsi_displacement.py`）が実装される前の経路で投入された既存データの
実態をそのまま反映している。API上は`fiscal_year_provenance`が`"unknown"`
として表示される状態に相当する。将来この入力データを再ingestし来歴を
埋め直す場合は、本snapshotおよび下記の期待値も更新が必要になる。

## 再現方法

```sh
./scripts/reproduce.sh
```

開発中の`docker compose up`環境（db:5432, backend:8000）には一切触れず、
別のCompose project名（`sinkscope-reproduce`）・別ホストポート
（15432 / 18000）を使った使い捨て環境で実行し、成功・失敗を問わず終了時に
必ず破棄する。前提として`.env`が存在すること（`cp .env.example .env`）。

## 検証済みの実行（事実）

2026-07-23、上記手順をローカルで実行し、以下を確認した:

- 正常系: 全指標（`p_value_one_sided=0.9616`, `morans_i=0.7970697398773147`,
  `baseline_road_length_spearman_rho=0.903368503464283`,
  `pipe_count=51084`, `in_aoi_event_count=129`,
  `in_aoi_sewer_event_count=30`）が期待値と一致し、`SUCCESS`で終了。
- 異常系: 期待値ファイルの1値を意図的に改変して実行し、
  `CommandError`・差分表示（`expected=... actual=...`）・非ゼロ終了で
  確実に失敗する（drift検知）ことを確認。
- 両方の実行後、開発中のDB（`AnalysisRun`4件・`TriageRun`2件）が
  変化していないことを確認済み。

## このスナップショットの限界

- 特定時点（2026-07-23、AnalysisRun #4 / TriageRun #2 時点）の入力データの
  固定化であり、GSI/OSM等のライブソースを今すぐ再取得した場合の値ではない。
  「今のインターネット上の最新データで同じ結論が出るか」ではなく、
  「ASSESSMENT.mdに書いた数値が捏造や計算ミスでなく、実際にこの入力から
  この手順で導かれることを誰でも確認できるか」を保証するものである。
- `SyntheticPipe`（Illustrative）はOverpass APIから取得した実際の道路
  ジオメトリを元にしているが、布設年・管種は架空値であることに変わりない。
