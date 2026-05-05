# Git Workflow Rules — HYLIST

> **Đọc khi:** commit, branch, merge, DVC push, MLflow version, ADR

---

## Conventional Commits — BẮT BUỘC

```
<type>(<scope>): <description>

[optional body — dùng cho model promotion, breaking changes]
[optional footer — BREAKING CHANGE, closes #issue]
```

### Commit Types

| Type | Khi nào dùng | Ví dụ scope |
|------|-------------|-------------|
| `feat` | Tính năng mới | `tasks`, `auth`, `kanban` |
| `fix` | Bug fix | `api`, `prediction`, `nlp` |
| `refactor` | Cải thiện code, không đổi behavior | `service`, `schema` |
| `chore` | Config, deps, tooling | `docker`, `deps`, `ci` |
| `docs` | Documentation, ADR | `adr`, `readme`, `retro` |
| `test` | Thêm/sửa test | `unit`, `integration`, `ml` |
| `perf` | Performance improvement | `query`, `cache`, `index` |
| `ml` | Training pipeline, features, hyperparams | `predictor`, `extractor` |
| `data` | Dataset changes (PHẢI kèm dvc push) | `tasks`, `augment` |
| `model` | Deploy/promote model version | `predictor` |
| `agent` | Agent tools, prompts, HITL rules | `research`, `tools` |
| `ci` | CI/CD changes | `github-actions`, `makefile` |

### Ví dụ thực tế

```bash
feat(tasks): add context_switch_count field + Alembic migration
fix(prediction): handle null actual_time in drift monitor
ml(predictor): retrain xgboost v1.2, val_mae=1.1h, dataset=v2.0
data(tasks): add 10k LLM-augmented samples via GPT-4o, total=50k
model(predictor): promote v1.2 from shadow to production
agent(research): add arxiv.org to SafeWebCrawler allowlist
docs(adr): add ADR-003 why we chose SetFit over full fine-tuning
chore(deps): upgrade pydantic 2.7 → 2.8, no breaking changes
test(ml): add training-serving parity test for TaskFeatureExtractor
```

### Sẽ bị commitlint chặn

```bash
"fix bug"              # ❌ thiếu type
"FEAT: add login"      # ❌ type phải lowercase
"feat: "               # ❌ thiếu description
"ml: retrain model"    # ❌ thiếu scope
```

---

## Branch Strategy

```
main        ← Production (protected — chỉ merge qua PR sau CI pass)
develop     ← Staging (protected — feature branches merge vào đây)
feat/*      ← Feature branches (tạo từ develop)
fix/*        ← Bug fix branches
ml/*        ← ML experiment branches (tạo từ develop)
data/*      ← Dataset update branches (PHẢI kèm dvc push)
hotfix/*    ← Emergency fix (từ main — merge vào cả main và develop)
```

**Flow chuẩn:**
```bash
git checkout develop
git pull origin develop
git checkout -b feat/task-prediction-card
# ... code ...
git push origin feat/task-prediction-card
# Tạo PR → develop (CI must pass) → Squash Merge
```

---

## DVC + MLflow Commit Rules (QUAN TRỌNG)

### Commit type `data`

```bash
# PHẢI thực hiện đúng thứ tự này:
dvc add ml/data/tasks_training.csv      # Track file
dvc push                                 # Upload lên remote storage TRƯỚC
git add ml/data/tasks_training.csv.dvc
git commit -m "data(tasks): add 10k GPT-augmented samples, total=50k, source=gpt-4o"
git tag dataset-v2.0                     # Tag version

# PHẢI có trong commit message:
# - Số records thêm vào
# - Total records sau khi thêm
# - Nguồn data (manual/LLM/scrape)
```

### Commit type `model`

```bash
# Commit body BẮT BUỘC phải có:
git commit -m "model(predictor): promote v1.2 from shadow to production" << 'EOF'

MLflow run_id: abc123def456789
Previous stage: Shadow (7 days, 2026-04-27 → 2026-05-04)
Metrics comparison:
  prod_mae:   1.45h
  shadow_mae: 1.12h (improvement: 22.8%)
DVC dataset: dataset-v2.0 (50k samples)
Approved by: @senior-review
EOF

# KHÔNG promote trực tiếp Staging → Production
# BẮT BUỘC: Staging → Shadow (1 tuần) → Production
```

### Commit type `ml`

```bash
# Phải ghi metrics vào commit body
git commit -m "ml(predictor): add deadline_buffer_hrs feature, retrain

Experiment: xgboost-20260504-1430 (MLflow run_id: xyz789)
Dataset: dataset-v2.0 (50k samples)
New feature: deadline_buffer_hrs (importance rank: #2)
Metrics:
  val_mae:  1.45h → 1.12h (-22.8%)
  val_rmse: 2.1h  → 1.8h  (-14.3%)
Training time: 4m 32s"
```

---

## Pull Request Rules

```
PR title PHẢI là Conventional Commit format:
  ✅ "feat(tasks): add Kanban board drag-and-drop"
  ❌ "Add kanban feature"

PR checklist (tự check trước khi request review):
  [ ] CI pass: pytest --cov-fail-under=70
  [ ] tsc --noEmit pass (frontend)
  [ ] Không có TODO/FIXME còn sót
  [ ] Alembic migration đã tạo nếu đổi schema
  [ ] KHÔNG commit .env, credentials, hay model weights
  [ ] DVC push nếu dataset thay đổi
  [ ] ADR đề xuất nếu có quyết định kiến trúc mới
```

---

## ADR Decision Framework

### Khi nào TẠO ADR

| Tình huống | Ví dụ HYLIST |
|-----------|-------------|
| Chọn thư viện mới | Thêm SetFit thay vì full fine-tune |
| Kiến trúc có phạm vi lớn | NLP Worker thành container riêng |
| Trade-off rõ ràng | SSE vs WebSocket cho real-time |
| Từ chối một approach | Không dùng pickle vì security risk |

### ADR đã có trong HYLIST

- `ADR-001` — SSE thay vì WebSocket (đơn giản hơn, HTTP-compatible)
- `ADR-002` — ONNX thay vì pickle (security + cross-platform)
- `ADR-003` — SetFit thay vì full fine-tune (ít data, nhanh)

### KHÔNG cần ADR

Bug fix, refactor, thêm field, thay đổi UI/style, bump dependency.

---

## Pre-commit Hooks (tự động khi `git commit`)

```
hooks chạy:
  ruff check --fix     ← Python linting + auto-fix
  mypy backend/src/    ← Type checking
  commitlint           ← Conventional Commits format
  gitleaks detect      ← Scan secrets (block nếu phát hiện)
```

---

## Self-Check

```
[ ] Commit message đúng Conventional Commits format
[ ] Branch từ develop (không từ main)
[ ] CI pass: pytest + tsc --noEmit
[ ] Alembic migration đã tạo nếu đổi schema
[ ] DVC push nếu dataset thay đổi (commit type "data")
[ ] MLflow run_id ghi vào commit body (commit type "model")
[ ] Metrics ghi vào commit body (commit type "ml")
[ ] KHÔNG có .env, secrets, model weights trong commit
[ ] ADR đề xuất nếu có quyết định kiến trúc mới
[ ] Squash merge vào develop (giữ history sạch)
```
