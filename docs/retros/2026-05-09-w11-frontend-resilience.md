# Retro: W11 — Phase 3 Frontend + Resilience + Quality Gates

**Date:** 2026-05-09
**Phase:** Phase 3 (NLP + Real-time)
**Sprint:** W11/16

---

## 1. Mục Tiêu Đã Đạt

### Backend Quality (hoàn thành trước khi frontend)
- **RFC 7807 Problem Details** (`core/errors.py`): Chuẩn hóa error responses theo Stripe/GitHub/Shopify. Field-level validation errors, `application/problem+json` media type.
- **Circuit Breaker + Timeout** (`core/resilience.py`): 3-state FSM (CLOSED/OPEN/HALF_OPEN), exponential backoff retry. Singletons: ml_circuit (5s), redis_circuit (2s), nlp_circuit (10s). **Fail fast > hang forever.**
- **CI/CD migrate sang uv**: `astral-sh/setup-uv@v5`, cache keyed on `uv.lock`, mới: `lock-check` job (phát hiện pyproject.toml changed mà không chạy `uv lock`). Concurrency groups.
- **Test coverage**: 64 → 88 tests, 68% → 73% overall. `ml_service.py` 30% → 57%. `resilience.py` 89%.

### Frontend Phase 3 (hoàn thành trong W11)
- **Auth System**: Zustand store (`lib/auth/session.ts`) với cookie persistence (js-cookie). Không dùng localStorage (XSS risk).
- **Login/Register pages**: Glassmorphism dark design. Zod validation. Error handling.
- **SSE Hook** (`hooks/useSSE.ts`): Exponential backoff reconnect (500ms → 30s). Token injection qua query param (EventSource không support headers — ADR-001). Dynamic event handlers.
- **Kanban Board**: SSE wired — optimistic update khi nhận `tags_updated`. Create Task modal với "AI will auto-tag" notice. Multi-column view.
- **TaskCard**: NLP tag badges màu riêng per class (Bug=red, Feature=blue, Urgent=orange, Research=violet). ML prediction badge (~4.5h). Animated pulse khi `isUpdating`.
- **Project Context**: Auto-fetch, auto-create default project cho new users. localStorage persistence.
- **Middleware**: Next.js Edge route protection. Cookie-based session check.
- **TypeScript**: 0 errors (`npx tsc --noEmit` clean).

---

## 2. Vấn Đề Gặp Phải

### C drive đầy (0.5GB)
- **Root cause**: uv cache mặc định lưu vào C (`%LOCALAPPDATA%\uv\cache`). scipy và ML deps nặng.
- **Tạm thời**: `uv cache clean` (giải phóng 112MB). Training SetFit bị block.
- **Fix vĩnh viễn**: Dọn C drive + `uv config set cache-dir D:\uv-cache`.

### useSSE signature mismatch
- KanbanBoard gọi `useSSE(url, handlers, enabled)` — 3 args.
- File mới viết dùng options object.
- **Fix**: Rewrite useSSE để match signature của KanbanBoard (giữ consumer, không bắt consumer thay đổi).

---

## 3. Architecture Decisions W11

| Quyết định | Lý do |
|-----------|-------|
| useSSE(url, handlers, enabled) — 3-arg | Consistent với existing KanbanBoard |
| getAuthClient(token) thay interceptor | Type-safe, không runtime errors |
| Cookie persistence (js-cookie) | SSE token cần accessible, không thể httpOnly |
| Circuit breaker as singleton | 1 CB per service, không tạo nhiều instances |

---

## 4. Next Steps (W12)

**Blocker cần giải quyết:**
1. Dọn C drive (user action)
2. `uv config set cache-dir D:\uv-cache`
3. Train SetFit model: `uv run --group nlp python ml/nlp/training/train_tagger.py`

**Sau khi có model:**
4. Update `nlp_worker.py` load từ local path
5. E2E test: Login → Create Task "Fix crash" → SSE cập nhật tag "Bug"
6. ML prediction test: task hiển thị "~2.0h" prediction

**W12 new features:**
7. Task detail drawer (click card → view SHAP values)
8. Shadow Mode dashboard endpoint (`GET /api/v1/ml/predictions`)
9. Test coverage `ml_service.py`: 57% → 70%
