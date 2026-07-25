# SinkScope 開発・デモ用タスク。
# `make help` で一覧。

.DEFAULT_GOAL := help
.PHONY: help demo seed reproduce test down

help: ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

demo: ## デモ環境を用意（build → DB起動 → migrate → golden snapshotからオフライン投入 → バックエンド起動）
	@test -f .env || cp .env.example .env
	docker compose build backend
	docker compose run --rm backend sh -c "python manage.py migrate && python manage.py seed_demo"
	docker compose up -d db backend
	@echo ""
	@echo "==> バックエンド起動: http://localhost:8000/api/health/"
	@echo "==> フロントは別ターミナルで:  cd frontend && npm install && npm run dev  → http://localhost:5173"
	@echo "    (単一URL配信は D7 で対応予定)"

seed: ## 既存のデモ環境へ golden snapshot を再投入（--force 相当）
	docker compose run --rm backend python manage.py seed_demo --force

reproduce: ## docs/ASSESSMENT.md の数値を使い捨て環境で再現・照合（開発DBには触れない）
	./scripts/reproduce.sh

test: ## バックエンドのテストスイートを実行
	docker compose run --rm backend python manage.py test

down: ## コンテナを停止・破棄（DBボリュームも削除）
	docker compose down -v
