#!/bin/sh
set -e

# docs/ASSESSMENT.md §2 の実測値(p値・Moran's I・道路長とのSpearman順位相関ρ)を、
# コミット済みのgolden snapshot(backend/analysis/fixtures/golden_snapshot.json.gz、
# 来歴はdocs/SNAPSHOT.md参照)から、独立した使い捨てのDocker Compose環境で再現する。
#
# `docker compose up`で動かしている開発中のdb/backendコンテナには一切触れず
# (別のCompose project名 "sinkscope-reproduce" を使う)、終了時は成功・失敗を
# 問わず必ず破棄する(trap EXIT)。

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "エラー: .env が見つかりません。先に 'cp .env.example .env' を実行してください。" >&2
  exit 1
fi

# 別のCompose project名("sinkscope-reproduce")と、開発中のdb(5432)/backend(8000)
# と衝突しないホストポートを使うことで、`docker compose up`で動かしている開発
# 環境に一切触れずに実行する(docker-compose.yml のDB_HOST_PORT/BACKEND_HOST_PORT
# 参照)。
export DB_HOST_PORT=15432
export BACKEND_HOST_PORT=18000
COMPOSE="docker compose -p sinkscope-reproduce"

cleanup() {
  echo "=== 使い捨て環境を破棄 ==="
  $COMPOSE down -v
}
trap cleanup EXIT

echo "=== backendイメージをビルド ==="
$COMPOSE build backend

echo "=== migrate ==="
$COMPOSE run --rm backend python manage.py migrate

echo "=== golden snapshotから再現・照合 ==="
$COMPOSE run --rm backend python manage.py reproduce_assessment
