# [2026-05-05] Project Setup — AI Context Layer

## Đã làm
- Setup HYLIST project từ `ai-harness-template` (min2hi/ai-harness-template)
- Điền đầy đủ `architecture/SKILL.md` với tech stack, ports, request flows, K8s roadmap
- Điền `backend/SKILL.md` với RBAC pattern, idempotency, AuditLog, ML-ready schema fields
- Điền `frontend/SKILL.md` với SSE hook, React Query, Zustand, auto-gen API client pattern
- Điền `ml/SKILL.md` với FeatureExtractor parity, MLflow, ONNX, drift monitoring
- Điền `agent/SKILL.md` với Budget Guard, AgentOutputValidator, HITL pattern
- Điền `testing/SKILL.md` với Testcontainers, parity tests, factory-boy
- Điền `git-workflow/SKILL.md` với commit types ml/data/model, DVC rules, ADR workflow
- Điền `docs/MEMORY.md` với stack thực tế, ADR index, sensitive code zones
- Tạo ADR-001 (SSE), ADR-002 (ONNX), ADR-003 (SetFit)
- Thêm onboarding block + Phase roadmap vào `AGENTS.md`

## Vấn đề gặp phải & cách giải quyết
- Template gốc còn hardcode "MediChain" và "HYLIST" trong header — đã sửa thành `{{PROJECT_NAME}}`
- `MEMORY.md` bị copy nguyên `{{placeholder}}` — đã điền thông tin thật
- Verify command trong AGENTS.md mơ hồ — đã tách cụ thể theo loại thay đổi (backend/frontend/ML/schema)
- PostgreSQL version mismatch (16 vs 17) trong testing SKILL — đã sửa

## Còn dang dở
- Chưa tạo thực tế code nào trong `backend/`, `frontend/`, `ml/` — chỉ setup AI context
- Chưa push HYLIST lên GitHub remote (chỉ có local git)
- Chưa tạo `openapi.yaml` contract
- Chưa setup `docker-compose.yml` và `Makefile`

## Phải nhớ buổi sau
- **QUAN TRỌNG:** `ml/features/task_extractor.py` là file CRITICAL — dùng chung train+serve. Sửa file này PHẢI chạy `pytest backend/tests/ml/ -v` (parity test) ngay lập tức
- `src/lib/api/` trong frontend là AUTO-GENERATED từ `openapi.yaml` — **KHÔNG SỬA TAY**
- Mọi table PHẢI có `org_id` (multi-tenancy) — thiếu là bug nghiêm trọng
- Soft delete (`deleted_at`) thay hard delete — cần data để train ML
- HYLIST đang ở Phase 1 (Tuần 1–4): Core API + Auth + Kanban + Observability
