# MEMORY.md — HYLIST Project Knowledge Index

> File này lưu lại CÁC QUYẾT ĐỊNH ĐÃ CHỐT của dự án.
> AI phải đọc file này vào đầu mỗi buổi làm việc.
> Cập nhật mỗi khi có quyết định kỹ thuật mới.

---

## Tech Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic
- **Frontend:** Next.js 15 (App Router) + TypeScript + React Query v5 + Zustand + SSE
- **Database:** PostgreSQL 17 (primary) + Redis 7 (cache, Celery broker, idempotency)
- **ML:** XGBoost + MLflow + ONNX Runtime + DVC + Great Expectations + SHAP
- **NLP:** SetFit + HuggingFace Transformers (auto-tagging: Bug/Feature/Urgent/Research)
- **Agent:** LangChain + Celery + Celery Beat (autonomous research agent)
- **Auth:** JWT (python-jose) + RBAC — Roles: ADMIN, MANAGER, MEMBER, VIEWER
- **Observability:** Prometheus + Grafana + OpenTelemetry + Sentry + structlog
- **Deploy:** Docker Compose (dev) → Docker Desktop Kubernetes (staging, Phase 4)
- **API Contract:** OpenAPI 3.0 (openapi.yaml) — contract-first, codegen frontend types
- **LLM:** OpenAI GPT-4o-mini + Budget Guard ($10/day/user limit)

---

## ADR Index — Các Quyết Định Kiến Trúc Đã Chốt

| ADR | Quyết định | Thay thế gì | Lý do chính |
|-----|-----------|-------------|-------------|
| ADR-001 | **SSE** thay WebSocket | WebSocket | Đơn giản hơn, HTTP-compatible, đủ cho one-way NLP tag updates |
| ADR-002 | **ONNX Runtime** thay pickle | pickle | Security risk (arbitrary code exec) + cross-platform + faster inference |
| ADR-003 | **SetFit** thay full fine-tuning | Full BERT fine-tune | Ít data hơn (10–50 samples/class), training nhanh, accuracy đủ dùng |

> Xem chi tiết trong `docs/adr/`

---

## Quyết Định Kỹ Thuật Đã Chốt (Không Cần ADR)

| Ngày | Quyết định | Lý do |
|------|-----------|-------|
| 2026-05-05 | Dùng `async_sessionmaker` + `session.begin()` — KHÔNG gọi `session.commit()` trong service | Auto rollback on error, tránh connection leak |
| 2026-05-05 | Soft delete thay hard delete (`deleted_at` timestamp) | Cần historical data để train ML model |
| 2026-05-05 | AuditLog qua middleware — KHÔNG ghi thủ công trong service | Consistency, không bỏ sót |
| 2026-05-05 | Idempotency-Key header bắt buộc cho POST/PUT | Tránh duplicate khi client retry |
| 2026-05-05 | API client auto-gen từ openapi.yaml — KHÔNG viết tay `src/lib/api/` | Single source of truth, type-safe |
| 2026-05-05 | ML features phải thiết kế từ Phase 1 (Tuần 1) | Không thể retro-fit features về sau |
| 2026-05-05 | NLP Worker chạy container riêng (Phase 3) | PyTorch dependencies nặng — không bundle vào main API |
| 2026-05-07 | `TaskFeatureExtractor` import lazy trong `MLService.initialize()` | Tránh kéo pandas vào CI backend-only env |
| 2026-05-07 | Model files (.onnx, .ubj) KHÔNG commit vào git — dùng DVC | Binary files làm git history bloat |
| 2026-05-07 | `get_db_context()` trong database.py cho Celery workers | Workers không có FastAPI Depends — cần context manager riêng |
| 2026-05-07 | SetFit model lưu trên HuggingFace Hub (MVP) → DVC sau khi fine-tune | Giảm binary size trong repo, dễ version |
| 2026-05-07 | **SetFit base model = `sentence-transformers/paraphrase-MiniLM-L3-v2`** | ~80MB, download khi nlp-worker startup, cache local sau đó |
| 2026-05-07 | NLP Worker Docker memory limit: tăng Docker Desktop lên 8GB | nlp-worker cần ~1.5-2GB PyTorch, tổng stack ~3GB |

---

## Vùng Code Nhạy Cảm — Hỏi Lại Trước Khi Sửa

| File / Module | Tại sao nhạy cảm |
|---------------|-----------------|
| `backend/src/core/auth.py` | JWT + RBAC — ảnh hưởng toàn bộ authentication/authorization |
| `backend/src/middleware/idempotency.py` | Sửa sai → duplicate records trong DB |
| `ml/features/task_extractor.py` | **CRITICAL** — dùng chung train + serve; sửa sai → Training-Serving Skew |
| `backend/src/core/database.py` | Connection pool + `get_db_context()` — sửa sai → connection leak hoặc timeout |
| `openapi.yaml` | Source of truth — sửa → phải chạy lại codegen frontend |
| `alembic/versions/` | KHÔNG sửa migration đã commit — tạo migration mới |

---

## Blockers & Vấn Đề Đang Mở

> Cập nhật khi gặp blocker chưa resolve

- *(Thêm vào đây khi gặp blocker)*

---

*Cập nhật lần cuối: 2026-05-07 (Phase 2 hoàn thành)*

| 2026-05-08 | SetFit training data generated: ml/data/nlp_training.csv (200 samples, 50/class) | Bootstrap data dung de cold-start NLP model |
| 2026-05-08 | Frontend auth: Zustand + js-cookie (cookie key: hylist_token), KHONG dung localStorage | XSS safer; SSE can doc token qua getToken() |
| 2026-05-08 | api client (client.ts) basePath = API_URL + /api/v1, auth paths dung native fetch thay vi openapi-fetch vi union type inference issue | openapi-fetch body la union cua tat ca POST endpoints, khong type-safe cho individual endpoints |
| 2026-05-08 | CORS_ORIGINS la env var, doc vao config.py qua cors_origins_list property | Khong hardcode origins |
