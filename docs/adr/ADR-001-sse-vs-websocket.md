# ADR-001: SSE thay vì WebSocket cho Real-time Updates

**Ngày:** 2026-05-05
**Trạng thái:** Accepted
**Người quyết định:** Team HYLIST

---

## Vấn đề (Context)

HYLIST cần push real-time updates từ server xuống client khi NLP tagging hoàn thành (Phase 3) và khi Agent tạo comment (Phase 4). Cần chọn giữa SSE và WebSocket.

## Đã xem xét (Options)

### A: Server-Sent Events (SSE)
- **Ưu:** HTTP/1.1 compatible, không cần upgrade protocol, tự động reconnect, đơn giản hơn, dễ debug qua browser DevTools, load balancer không cần config thêm, FastAPI hỗ trợ qua `sse-starlette`
- **Nhược:** Chỉ server → client (one-way), không dùng được cho bi-directional communication

### B: WebSocket
- **Ưu:** Bi-directional, full-duplex, latency thấp hơn
- **Nhược:** Phức tạp hơn, cần WebSocket-aware load balancer, sticky sessions, khó debug hơn, overkill cho use case hiện tại

## Quyết định (Decision)
**Chọn A (SSE)** vì HYLIST chỉ cần server → client push (NLP tags, Agent comments). Không có use case nào cần client → server stream. SSE đơn giản hơn, không cần config infrastructure thêm.

## Trade-off chấp nhận (Consequences)
Nếu sau này cần bi-directional real-time (ví dụ: collaborative editing), sẽ phải migrate sang WebSocket. Chấp nhận vì scope hiện tại không có use case đó.

---
> Xem implementation: `backend/src/api/v1/tasks.py` (tag-stream endpoint) và `frontend/src/hooks/useSSE.ts`
