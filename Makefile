.PHONY: dev down install migrate migration reset-db test test-unit test-ml lint format mock-data train dvc-push k8s-deploy k8s-status k8s-logs k8s-delete

# ─── Infrastructure ────────────────────────────────────────────────────────────
dev:                        ## Khởi chạy tất cả services (Postgres, Redis, Prometheus, Grafana)
	docker compose up -d
	@echo ""
	@echo "✅ Services đang chạy:"
	@echo "   API (local):  http://localhost:8000"
	@echo "   Grafana:      http://localhost:3001  (admin/admin)"
	@echo "   Prometheus:   http://localhost:9090"
	@echo "   Postgres:     localhost:5432"
	@echo ""

down:                       ## Tắt tất cả services
	docker compose down

logs:                       ## Xem logs realtime
	docker compose logs -f

# ─── Backend Python ────────────────────────────────────────────────────────────
install:                    ## Cài đặt Python dependencies
	cd backend && pip install -e ".[dev]"

run:                        ## Chạy FastAPI dev server (hot reload)
	cd backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# ─── Database Migrations ───────────────────────────────────────────────────────
migrate:                    ## Chạy migration mới nhất
	cd backend && alembic upgrade head

migration:                  ## Tạo migration mới: make migration name="add users table"
	cd backend && alembic revision --autogenerate -m "$(name)"

reset-db:                   ## ⚠️  Drop + recreate DB (CHỈ dùng local)
	cd backend && alembic downgrade base && alembic upgrade head

# ─── Testing ──────────────────────────────────────────────────────────────────
test:                       ## Chạy tất cả tests (coverage >= 70%)
	cd backend && pytest tests/ --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=70 -v

test-unit:                  ## Chỉ unit tests (nhanh)
	cd backend && pytest tests/unit/ -v

test-ml:                    ## ML parity tests (chạy sau khi đổi FeatureExtractor)
	cd backend && pytest tests/ml/ -v

test-contract:              ## Contract tests với OpenAPI spec
	schemathesis run --checks all openapi.yaml --base-url http://localhost:8000

# ─── Code Quality ─────────────────────────────────────────────────────────────
format:                     ## Auto-format + fix lint: chay truoc khi commit
	cd backend && ruff format src/ && ruff check src/ --fix
	@echo "Format done. Ready to commit."

check:                      ## Kiem tra format + lint (mirror CI) — khong sua file
	cd backend && ruff format --check src/ && ruff check src/

lint:                       ## Lint + type check
	cd backend && ruff check src/ && mypy src/

ci:                         ## Chay toan bo CI local: format-check + lint + tests
	@echo "=== [CI Local] ruff format ==="
	cd backend && ruff format --check src/
	@echo "=== [CI Local] ruff lint ==="
	cd backend && ruff check src/
	@echo "=== [CI Local] pytest ==="
	cd backend && pytest tests/ --cov=src --cov-fail-under=70 -q
	@echo ""
	@echo "CI Local: ALL PASSED"

# ─── ML Pipeline ──────────────────────────────────────────────────────────────
mock-data:                  ## Sinh 10k mock tasks (cần chạy trước khi train)
	cd backend && python -m ml.mock_generator

train:                      ## Train XGBoost model
	cd ml && python training/train_predictor.py

dvc-push:                   ## Push dataset lên DVC remote storage
	dvc push

# ─── Kubernetes (Phase 4) ─────────────────────────────────────────────────────
k8s-deploy:                 ## Deploy lên K8s cluster (Docker Desktop)
	kubectl apply -f k8s/

k8s-status:                 ## Xem trạng thái pods và services
	kubectl get pods,svc -n hylist-dev

k8s-logs:                   ## Follow logs của API pod
	kubectl logs -f deployment/hylist-api -n hylist-dev

k8s-delete:                 ## Xóa toàn bộ K8s resources
	kubectl delete -f k8s/

# ─── Help ─────────────────────────────────────────────────────────────────────
help:                       ## Hiển thị danh sách commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
