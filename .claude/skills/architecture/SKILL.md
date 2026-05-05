# HYLIST — Architecture Overview

> **Đọc file này khi:** hỏi về kiến trúc tổng thể, stack, luồng hệ thống, ports, service map.
> **Project:** Intelligent Task Orchestration System — 16-week roadmap

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) | Async-first, Pydantic v2 validation |
| Frontend | Next.js 15 (App Router) + TypeScript | Auto-gen types từ openapi.yaml |
| Database | PostgreSQL 17 | Primary DB — Alembic migrations |
| Cache / Queue | Redis 7 | Cache + Celery broker + pub/sub + idempotency |
| ORM | SQLAlchemy 2.0 async + Alembic | KHÔNG dùng Prisma hay raw SQL |
| Auth | JWT (python-jose) + RBAC middleware | Role: ADMIN, MANAGER, MEMBER, VIEWER |
| ML Engine | XGBoost + MLflow + ONNX Runtime | Tabular regression — predict task time |
| NLP | SetFit + HuggingFace Transformers | Task auto-tagging: [Bug][Feature][Urgent][Research] |
| Agent | LangChain + Celery + Celery Beat | Autonomous research agent |
| Observability | Prometheus + Grafana + OpenTelemetry + Sentry | Bắt buộc từ Tuần 1 |
| Data Version | DVC | Dataset versioning, liên kết với MLflow run |
| API Contract | OpenAPI 3.0 (openapi.yaml) | Contract-first — viết trước khi code |
| Rate Limiting | slowapi | Per-endpoint, per-user |
| Infra (Dev) | Docker Desktop + Docker Compose | `make dev` — fast local iteration |
| Infra (Staging) | Docker Desktop Kubernetes (built-in) | `make k8s-deploy` — học quản lý container qua K8s |

## Project Structure

```
hylist/
├── backend/                    ← FastAPI application (Python 3.12)
│   ├── src/
│   │   ├── api/
│   │   │   └── v1/             ← Routers (tasks, projects, users, predict, tags)
│   │   ├── services/           ← Business logic (không import Request/Response)
│   │   ├── models/             ← SQLAlchemy ORM models (org_id bắt buộc)
│   │   ├── schemas/            ← Pydantic v2 DTO + Response schemas
│   │   ├── middleware/         ← Auth, RBAC, AuditLog, Idempotency, RateLimit
│   │   ├── workers/            ← Celery tasks (nlp, agent, drift_monitor)
│   │   ├── core/               ← Config, DB session, security, redis client
│   │   └── main.py             ← FastAPI app entrypoint
│   ├── alembic/                ← Database migrations (KHÔNG dùng create_all)
│   ├── tests/
│   │   ├── unit/               ← test_*.py per service
│   │   ├── integration/        ← test FastAPI endpoints với DB thật
│   │   └── ml/                 ← test FeatureExtractor parity
│   └── pyproject.toml
├── frontend/                   ← Next.js 15 App Router (TypeScript)
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/         ← login, register pages
│   │   │   └── (dashboard)/    ← board, projects, tasks
│   │   ├── components/
│   │   │   ├── kanban/         ← KanbanBoard, TaskCard, Column
│   │   │   ├── task/           ← TaskForm, PredictionCard, TagBadge
│   │   │   └── agent/          ← AgentComment, HITLReviewCard
│   │   ├── hooks/              ← useTasks, useSSE, usePrediction
│   │   ├── lib/api/            ← Auto-gen từ openapi.yaml (KHÔNG sửa tay)
│   │   └── stores/             ← Zustand UI state
│   └── package.json
├── ml/                         ← ML training pipelines (Phase 2)
│   ├── features/
│   │   └── task_extractor.py   ← FeatureExtractor (shared train+serve) — CRITICAL
│   ├── training/
│   │   └── train_predictor.py  ← XGBoost training + MLflow tracking
│   ├── evaluation/
│   │   ├── data_validation.py  ← Great Expectations suites
│   │   └── drift_monitor.py    ← Production MAE monitoring
│   ├── data/                   ← DVC-tracked datasets (KHÔNG commit trực tiếp)
│   │   └── tasks_training.csv.dvc
│   └── mock_generator.py       ← Sinh 10k mock tasks (Phase 1, Tuần 4)
├── workers/                    ← NLP Worker — Container riêng (Phase 3)
│   ├── nlp_worker.py           ← SetFit inference + Redis Queue consumer
│   ├── requirements.txt        ← Dependencies riêng (PyTorch nặng)
│   └── Dockerfile
├── k8s/                        ← Kubernetes manifests (Phase 4 — học quản lý container)
│   ├── namespace.yaml           ← hylist-dev namespace
│   ├── configmap.yaml           ← Non-sensitive config
│   ├── secrets.yaml             ← Sensitive (KHÔNG commit — dùng kubectl create secret)
│   ├── deployments/
│   │   ├── api.yaml             ← FastAPI Deployment + HPA
│   │   ├── frontend.yaml        ← Next.js Deployment
│   │   ├── postgres.yaml        ← StatefulSet + PVC
│   │   ├── redis.yaml           ← Deployment
│   │   ├── celery-worker.yaml   ← Deployment (auto-scale theo queue)
│   │   └── nlp-worker.yaml     ← Deployment (GPU node selector — nếu có)
│   └── services/
│       ├── api-service.yaml     ← ClusterIP + Ingress
│       └── postgres-service.yaml
├── .claude/                    ← AI context & templates
├── .github/
│   └── workflows/
│       ├── ci.yml              ← Test + lint gate (block merge nếu fail)
│       └── deploy.yml          ← Deploy staging/production
├── docs/
│   ├── adr/                    ← Architecture Decision Records
│   │   ├── ADR-000-template.md
│   │   ├── ADR-001-sse-vs-websocket.md
│   │   └── ADR-002-onnx-vs-pickle.md
│   ├── retros/                 ← Session retrospectives
│   └── MEMORY.md               ← Technical decisions index
├── openapi.yaml                ← Source of truth — viết TRƯỚC khi code
├── docker-compose.yml
├── Makefile
└── AGENTS.md
```

## Service Map (Docker Compose Ports)

| Service | Port | Container Name | Phase |
|---------|------|----------------|-------|
| FastAPI Backend | 8000 | `hylist-api` | Phase 1 |
| Next.js Frontend | 3000 | `hylist-web` | Phase 1 |
| PostgreSQL 17 | 5432 | `hylist-postgres` | Phase 1 |
| Redis 7 | 6379 | `hylist-redis` | Phase 1 |
| Prometheus | 9090 | `hylist-prometheus` | Phase 1 |
| Grafana | 3001 | `hylist-grafana` | Phase 1 |
| Sentry (self-hosted) | 9000 | `hylist-sentry` | Phase 1 |
| MLflow Tracking | 5001 | `hylist-mlflow` | Phase 2 |
| Celery Flower | 5555 | `hylist-flower` | Phase 2 |
| NLP Worker | 8001 | `hylist-nlp` | Phase 3 |

> **Internal services** (NLP Worker, Celery) không expose port ra ngoài Docker network.

## Request Flow — Synchronous

```
Browser / Client
  ↓  HTTPS
slowapi Rate Limiter (30 req/min default)
  ↓
FastAPI Router /api/v1/<resource>
  ↓
Middleware Stack (thứ tự quan trọng):
  1. AuthMiddleware      → verify JWT, attach user to request
  2. RBACMiddleware      → check role permissions
  3. IdempotencyMiddleware → check Redis cache cho POST/PUT
  4. AuditLogMiddleware  → ghi lại mọi state change vào audit_logs
  ↓
Dependency Injection:
  get_current_user()    → CurrentUser(id, org_id, role)
  get_db()              → AsyncSession (auto rollback on error)
  ↓
Service Layer (business logic — không có HTTP objects)
  ↓
SQLAlchemy async query → PostgreSQL
  ↓
Response: { success: bool, data: T, message?: str }
```

## Request Flow — Async (NLP Tagging)

```
POST /api/v1/tasks/  →  Task created in DB
  ↓
AuditLog middleware ghi lại
  ↓
Celery task: enqueue_nlp_task(task_id)
  ↓ Redis Queue "nlp"
NLP Worker (container riêng) nhận job
  ↓
SetFit model: classify description → tags [Bug/Feature/Urgent/Research]
  ↓
Write tags back to DB
  ↓
Publish SSE event: "task:{task_id}:tags_updated"
  ↓
Frontend SSE hook nhận → optimistic update Kanban card (không reload)
```

## Request Flow — Agent (Phase 4)

```
Task tagged [Research]
  ↓
AuditLog trigger → Celery task: research_agent_task(task_id)
  ↓ Redis Queue "agent"
Budget Guard check: user daily spend < $10 USD
  ↓
LangChain Agent: research using SafeWebCrawler (allowlist domains)
  ↓
Output → AgentOutputValidator (PII, toxicity, length check)
  ↓
if confidence >= 0.95:  auto_apply_comment(task_id)
else:                   create_pending_review(task_id) + notify_assignee
```

## Multi-Tenancy Design

```
Mọi table đều có: org_id UUID NOT NULL REFERENCES organizations(id)

Service layer LUÔN filter:
  stmt = select(Task).where(Task.org_id == user.org_id, ...)

PostgreSQL RLS (Row Level Security) — bật trên production:
  CREATE POLICY tenant_isolation ON tasks
      USING (org_id = current_setting('app.current_org_id')::UUID);
```

## API Versioning

```
Base: /api/v1/
Breaking changes → /api/v2/ (song song, không xóa v1 ngay)
Deprecation header: Deprecation: Sat, 01 Jan 2027 00:00:00 GMT
Sunset header:      Sunset: Sun, 01 Jan 2028 00:00:00 GMT
```

## SLO Targets (Service Level Objectives)

| Metric | Target | Alert threshold |
|--------|--------|-----------------|
| API availability | 99.9% | < 99.5% |
| API p95 latency | < 200ms | > 400ms |
| /api/predict p95 | < 500ms | > 1000ms |
| NLP tagging e2e | < 5s | > 10s |
| Production MAE | < 2.0h | > 3.0h (trigger retrain) |

## Key User Flows

1. **Auth:** Register → verify email → login → JWT (`org_id`, `role`, `exp`)
2. **Task CRUD:** Create Task → AuditLog → NLP auto-tag → SSE update Kanban
3. **Prediction:** Create Task → `/api/predict` → estimated_hours + SHAP explanation
4. **Research Agent:** Tag [Research] → Celery → Agent research → HITL review/auto-comment
5. **ML Lifecycle:** Drift detected → retrain trigger → Shadow mode (1 week) → promote

## Environment Variables

```bash
# Core
DATABASE_URL=postgresql+asyncpg://hylist:secret@localhost:5432/hylist_db   # PG17 local
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<32-byte random>

# Auth
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# ML / MLflow
MLFLOW_TRACKING_URI=http://localhost:5001
ONNX_MODEL_PATH=ml/models/predictor_latest.onnx
DRIFT_THRESHOLD_MAE=2.0

# LLM / Agent
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini        # Cost-efficient default
LLM_DAILY_BUDGET_USD=10.0

# Observability
SENTRY_DSN=https://...@sentry.io/...
PROMETHEUS_PORT=9090

# Feature Flags
SHADOW_MODE_ENABLED=true
HITL_CONFIDENCE_THRESHOLD=0.95
```

> Xem `.env.example` để biết danh sách đầy đủ. **KHÔNG BAO GIỜ commit `.env` vào git.**

## Makefile Commands

```bash
make dev          # docker-compose up + seed data
make test         # pytest --cov=src --cov-fail-under=70
make migrate      # alembic upgrade head
make lint         # ruff check + mypy
make reset-db     # Drop + recreate + seed (chỉ dùng local)
make mock-data    # Chạy ml/mock_generator.py → 10k tasks
make train        # Chạy ml/training/train_predictor.py
make dvc-push     # dvc push (sau khi thêm dataset)

# Kubernetes (Phase 4)
make k8s-deploy   # kubectl apply -f k8s/
make k8s-status   # kubectl get pods,svc -n hylist-dev
make k8s-logs     # kubectl logs -f deployment/hylist-api -n hylist-dev
make k8s-delete   # kubectl delete -f k8s/
```

## Kubernetes Setup (Docker Desktop Built-in)

> **Bật K8s:** Docker Desktop → Settings → Kubernetes → ✅ Enable Kubernetes → Apply & Restart
> **Verify:** `kubectl cluster-info` — phải thấy `kubernetes` running

### Dev Workflow — 2 Mode Song Song

```
Mode 1 — Docker Compose (daily dev):
  make dev  →  docker-compose up
  Dùng khi: code mới, iterate nhanh

Mode 2 — Kubernetes (learning + staging simulation):
  make k8s-deploy  →  kubectl apply -f k8s/
  Dùng khi: học K8s, test manifest, simulate staging
```

### K8s Concepts Học Qua HYLIST

```
Pod           → 1 container instance (FastAPI, Redis, NLP Worker...)
Deployment    → Quản lý N replicas + rolling update (zero-downtime)
StatefulSet   → PostgreSQL — cần stable storage (PVC)
Service       → Expose Pod nội bộ (ClusterIP)
Ingress       → Route traffic ngoài → Service (thay nginx)
ConfigMap     → Non-sensitive env vars
Secret        → DB password, JWT key, API keys (base64 encoded)
PVC           → Persistent Volume Claim — lưu dữ liệu PostgreSQL
HPA           → Auto-scale Celery worker theo queue depth
Namespace     → Isolate: hylist-dev / hylist-staging
```

### K8s Cheat Sheet

```bash
# Xem trạng thái
kubectl get pods,svc -n hylist-dev
kubectl describe pod <pod-name> -n hylist-dev

# Logs
kubectl logs -f deployment/hylist-api -n hylist-dev
kubectl logs -f deployment/celery-worker -n hylist-dev

# Debug vào pod
kubectl exec -it <pod-name> -n hylist-dev -- /bin/bash

# Port-forward (test local)
kubectl port-forward svc/hylist-api 8000:8000 -n hylist-dev

# Deploy & update
kubectl apply -f k8s/
kubectl rollout restart deployment/hylist-api -n hylist-dev
kubectl rollout status deployment/hylist-api -n hylist-dev

# Scale
kubectl scale deployment/celery-worker --replicas=3 -n hylist-dev
```

### Lộ Trình Học K8s Trong Phase 4 (Tuần 13–16)

```
Tuần 13: Namespace + ConfigMap + Secret + Deployment đơn giản (API)
Tuần 14: Service + Ingress + Frontend Deployment
Tuần 15: StatefulSet PostgreSQL + PVC + health checks
Tuần 16: HPA Celery worker + rolling update + kubectl debug
```

