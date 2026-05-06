# HYLIST — AI Agent Context

> **Entry point duy nhất cho AI context.**
> Đọc section này trước, sau đó đọc SKILL.md tương ứng với task.

---

## 🚀 Bắt Đầu Buổi Làm Việc Mới (BẮT BUỘC)

```
1. Đọc docs/retros/ — file gần nhất để biết context buổi trước
2. Đọc docs/MEMORY.md — stack đã chốt + ADR index + vùng code nhạy cảm
3. Xác định task thuộc Phase nào (Phase 1–4) trong roadmap 16 tuần
4. Chỉ sau đó mới bắt đầu code
```

**Roadmap summary:**
- Phase 1 (Tuần 1–4): Core API + Auth + Kanban + Observability
- Phase 2 (Tuần 5–8): ML Engine — XGBoost predict + MLflow + SHAP
- Phase 3 (Tuần 9–12): NLP Auto-tagging (SetFit) + SSE real-time
- Phase 4 (Tuần 13–16): LangChain Agent + HITL + Kubernetes

> Nếu không rõ task thuộc Phase nào → hỏi user trước khi code.

## Skills Directory

| Khi làm việc với... | Đọc skill file này |
|--------------------|-------------------|
| Kiến trúc tổng thể, stack, ports, luồng hệ thống | `.claude/skills/architecture/SKILL.md` |
| Backend (`backend/src/**`) — FastAPI, SQLAlchemy, Celery | `.claude/skills/backend/SKILL.md` |
| Frontend (`frontend/src/**`) — Next.js, React Query, SSE | `.claude/skills/frontend/SKILL.md` |
| ML Pipeline — training, MLflow, ONNX, SHAP, drift | `.claude/skills/ml/SKILL.md` |
| Agent & LLM — LangChain, HITL, Budget Guard, tools | `.claude/skills/agent/SKILL.md` |
| Tạo file test, mock data, fixtures, factories | `.claude/skills/testing/SKILL.md` |
| Git commit, DVC, MLflow versioning, workflow | `.claude/skills/git-workflow/SKILL.md` |

## Templates Directory

> Khi tạo Service/Router/Schema **mới**, PHẢI copy từ template và thay thế placeholder.

| Khi tạo... | Dùng template này |
|-----------|------------------|
| Python Service mới | `.claude/templates/service.template.py` |
| Python Router mới | `.claude/templates/router.template.py` |
| Pydantic Schema mới | `.claude/templates/schema.template.py` |
| SQLAlchemy Model mới | `.claude/templates/model.template.py` |
| Celery Task mới | `.claude/templates/celery_task.template.py` |

**Quy trình tạo feature mới (Python backend):**
```
1. Copy model.template.py    → backend/src/models/<tên>.py
2. Copy schema.template.py   → backend/src/schemas/<tên>.py
3. Copy service.template.py  → backend/src/services/<tên>.service.py
4. Copy router.template.py   → backend/src/api/v1/<tên>.py
5. Tìm-Thay "Example"/"example" → tên feature của bạn
6. Đăng ký router trong backend/src/main.py
7. Tạo Alembic migration: alembic revision --autogenerate -m "add <tên> table"
8. Xóa các comment hướng dẫn
```

## Git Workflow — BẮT BUỘC (Không có ngoại lệ)

> **main là nhánh PRODUCTION. KHÔNG BAO GIỜ push thẳng lên main.**
> Mọi thay đổi, dù nhỏ đến đâu, phải đi qua Pull Request.

### Quy Trình Bắt Buộc

```
1. Tạo nhánh từ develop (hoặc main nếu chưa có develop):
     git checkout -b feat/<tên-tính-năng>     # Feature mới
     git checkout -b fix/<mô-tả-bug>          # Bug fix
     git checkout -b refactor/<phạm-vi>       # Refactor
     git checkout -b chore/<tên>              # Config, CI, docs

2. Code + commit theo Conventional Commits:
     git commit -m "feat(auth): add refresh token rotation"
     git commit -m "fix(db): handle NullPool for SQLite in tests"

3. Push nhánh phụ (KHÔNG phải main):
     git push origin feat/<tên-tính-năng>

4. Tạo Pull Request trên GitHub → target: main hoặc develop

5. Đợi CI xanh (🔐 Security + 🧪 Tests + 🔍 Lint) → ✅ CI Pass

6. Self-review diff một lần → điền PR checklist → Merge

7. Xóa nhánh sau khi merge (GitHub tự làm nếu bật tùy chọn)
```

### Naming Convention

| Loại | Prefix | Ví dụ |
|------|--------|-------|
| Feature | `feat/` | `feat/ml-priority-predictor` |
| Bug fix | `fix/` | `fix/no-such-table-sqlite` |
| Refactor | `refactor/` | `refactor/lazy-engine-factory` |
| Hotfix | `hotfix/` | `hotfix/jwt-expiry-critical` |
| CI/Infra | `chore/` | `chore/add-branch-protection` |

### AI KHÔNG ĐƯỢC

```
❌  git push origin main
❌  git push origin master
❌  Commit thẳng lên main dù bằng cách nào
❌  Bỏ qua CI failure và force merge

✅  git push origin feat/<tên>
✅  Tạo PR → đợi CI xanh → merge
```



## Hard Limits — Giới Hạn Cứng Cho AI

| Loại task | Tối đa dòng thay đổi | Tối đa commit |
|-----------|:--------------------:|:-------------:|
| Bug fix | 50 dòng | 1 commit |
| Refactor | 150 dòng | 1 commit |
| Feature mới | 300 dòng | Chia nhỏ |

- **Tối đa 400 dòng/file.** Nếu file sắp vượt → tách logic ra file mới trước khi thêm.
- **Không viết function dài hơn 50 dòng.** Dài hơn → phải extract ra hàm con.

### Quy tắc xác nhận

```
AI KHÔNG ĐƯỢC báo "xong" nếu chưa:
  1. Chạy lệnh verify phù hợp:
       Backend đổi:  make test   (pytest --cov=src --cov-fail-under=70)
       Frontend đổi: tsc --noEmit (trong frontend/)
       Schema đổi:   make migrate + make test
       ML đổi:       pytest backend/tests/ml/ -v  (parity test)
  2. Dán output thực tế của lệnh đó vào chat
  3. Nếu output có lỗi → phải fix xong, không được bỏ qua
```

## ADR — Khi Nào Phải Tạo

> Template: `docs/adr/ADR-000-template.md`

AI **BẮT BUỘC đề xuất tạo ADR mới** khi:

| Tình huống | Ví dụ |
|-----------|-------|
| Chọn thư viện/framework mới | Thêm `SetFit`, đổi từ `pickle` sang `ONNX` |
| Thay đổi kiến trúc có phạm vi lớn | Thêm NLP Worker service, tách Celery queue |
| Quyết định trade-off rõ ràng | Chọn SSE thay vì WebSocket |
| Từ chối một cách tiếp cận | "Không dùng pickle vì security risk" |

**ADR đã có trong HYLIST** (xem `docs/adr/`):
- ADR-001: SSE thay WebSocket
- ADR-002: ONNX thay pickle
- ADR-003: SetFit thay full fine-tuning

AI **KHÔNG cần tạo ADR** cho: bug fix, refactor nhỏ, thêm field, thay đổi UI/style, bump dependency version.

## Memory System

```
docs/
├── MEMORY.md              ← Index tổng hợp mọi quyết định đã ghi nhớ
└── retros/
    └── YYYY-MM-DD-topic.md ← Nhật ký sau mỗi buổi làm việc quan trọng
```

**Bắt đầu buổi làm việc mới:**
```
1. Đọc file retro gần nhất trong docs/retros/
2. Đọc MEMORY.md để biết các quyết định đã chốt
3. Chỉ sau đó mới bắt đầu code
```

## Self-Check Trước Khi Kết Thúc Task

```
IMPACT ANALYSIS
[ ] Đã chạy impact analysis (grep) trước khi sửa BẤT KỲ hàm cũ nào
[ ] Tất cả d=1 callers đã được cập nhật đồng thời

CODE QUALITY
[ ] Đã đọc SKILL.md tương ứng với task
[ ] Không có file test/mock/seed còn sót lại
[ ] Không có print/console.log debug trong production code
[ ] Không có hardcoded secrets
[ ] Không có import unused

BACKEND (Python)
[ ] Response format đúng chuẩn {success, data?, message?, error_code?}
[ ] Service không chứa Request/Response imports
[ ] Mọi query filter theo org_id (multi-tenancy)
[ ] Mọi user resource filter theo user.id (IDOR)
[ ] DB session dùng Depends(get_db) pattern
[ ] Protected routes có require_role() dependency
[ ] Alembic migration đã tạo nếu schema thay đổi

ML / AGENT
[ ] FeatureExtractor dùng chung cho train và serve
[ ] LLM call có budget_guard.can_execute() check
[ ] Agent output qua validator.validate() trước khi lưu
[ ] Tool sandbox có allowlist
[ ] HITL: confidence < 0.95 → pending_review

TEMPLATES & ADR
[ ] Nếu tạo Service/Router/Schema mới → đã dùng template Python
[ ] Nếu có quyết định kiến trúc mới → đã tạo hoặc đề xuất ADR

HARD LIMITS
[ ] Số dòng thay đổi không vượt giới hạn
[ ] Không có file nào vượt 400 dòng sau khi chỉnh sửa
[ ] Đã chạy lệnh verify và paste output thực tế vào chat

MEMORY SYSTEM
[ ] Nếu buổi làm việc quan trọng → đã tạo retro trong docs/retros/
[ ] Nếu có quyết định kỹ thuật mới → đã cập nhật MEMORY.md
```
