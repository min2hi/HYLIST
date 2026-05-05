# Backend Development Rules — HYLIST

> **Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 + Redis
> **Đọc khi:** viết API, service, model, migration, middleware

---

## ⛔ Impact Analysis — BẮT BUỘC trước khi sửa code cũ

```bash
# Bước 1: Tìm tất cả nơi dùng function/class cần sửa
grep -r "function_name" backend/src/

# Bước 2: Phân loại
#   d=1 (WILL BREAK): caller trực tiếp → PHẢI cập nhật cùng commit
#   d=2 (LIKELY AFFECTED): caller gián tiếp → phải test

# Bước 3: Nếu d=1 callers > 3 → báo user trước khi sửa
```

---

## Architecture Pattern

```
Request
  ↓ slowapi rate limiter
FastAPI Router  /api/v1/<resource>
  ↓ Middleware: Auth → RBAC → Idempotency → AuditLog
Dependency Injection: get_current_user(), get_db()
  ↓
Service Layer   (business logic — KHÔNG có Request/Response)
  ↓
SQLAlchemy async → PostgreSQL
```

**Phân tách trách nhiệm:**
- **Router**: Định nghĩa path, method, dependencies, rate limit. KHÔNG có logic.
- **Service**: Business logic thuần. KHÔNG import `Request`, `Response`, `HTTPException`.
- **Repository/Query**: Dùng `select()` với chỉ các field cần thiết. KHÔNG `select *`.

---

## Standard Response Format

```python
# Mọi endpoint phải trả về format này — không trả raw dict hay list

# schemas/common.py
from pydantic import BaseModel
from typing import Generic, TypeVar
T = TypeVar("T")

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str | None = None

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str | None = None    # e.g. "TASK_NOT_FOUND", "BUDGET_EXCEEDED"
    details: dict | None = None      # validation errors chi tiết

# Router usage:
@router.post("/", response_model=SuccessResponse[TaskOut], status_code=201)
async def create_task(...) -> SuccessResponse[TaskOut]:
    result = await service.create(dto, current_user)
    return SuccessResponse(data=result)
```

---

## DB Session Pattern (BẮT BUỘC — tránh connection leak)

```python
# core/database.py
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,     # Tự reconnect nếu connection chết
    pool_recycle=3600,      # Recycle sau 1 giờ
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
# ✅ Session tự đóng và rollback khi có lỗi
# ❌ KHÔNG dùng session.commit() trong service — commit do begin() transaction
```

---

## Service Layer Pattern

```python
# services/task.service.py
class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, dto: CreateTaskDto, user: CurrentUser) -> TaskOut:
        # 1. Validate input
        if not dto.title.strip():
            raise ValueError("Title không được để trống")

        # 2. Business logic — set org_id từ JWT, không từ body
        task = Task(
            org_id=user.org_id,        # BẮT BUỘC — multi-tenancy
            created_by=user.id,
            title=dto.title.strip(),
            priority_score=dto.priority,
            estimated_time=dto.estimated_hours,
        )
        self.db.add(task)
        await self.db.flush()  # Get ID without commit

        # 3. Trigger async NLP tagging
        from ..workers.nlp_tasks import enqueue_nlp_tagging
        enqueue_nlp_tagging.delay(str(task.id))

        logger.info("task_created", task_id=str(task.id), org_id=str(user.org_id))
        return TaskOut.model_validate(task)
```

---

## Router Pattern (đầy đủ)

```python
# api/v1/tasks.py
router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=SuccessResponse[TaskOut], status_code=201)
@limiter.limit("30/minute")
async def create_task(
    request: Request,                                    # slowapi cần
    dto: CreateTaskDto,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    # Idempotency: tránh tạo duplicate khi client retry
    cached = await redis_client.get(f"idem:{idempotency_key}")
    if cached:
        return json.loads(cached)                        # 200, không phải 201

    service = TaskService(db)
    result = await service.create(dto, current_user)
    response = SuccessResponse(data=result)

    # Cache 24h
    await redis_client.setex(f"idem:{idempotency_key}", 86400, response.model_dump_json())
    return response
```

---

## RBAC Pattern

```python
# core/auth.py
from enum import Enum

class Role(str, Enum):
    ADMIN   = "ADMIN"     # Xóa org, manage users
    MANAGER = "MANAGER"   # Manage projects, assign tasks
    MEMBER  = "MEMBER"    # CRUD tasks của bản thân
    VIEWER  = "VIEWER"    # Read-only

def require_role(*roles: Role):
    """FastAPI dependency — dùng trong router."""
    async def dependency(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(403, "Không đủ quyền")
        return current_user
    return dependency

# Dùng:
Depends(require_role(Role.ADMIN))              # Chỉ Admin
Depends(require_role(Role.MANAGER, Role.ADMIN)) # Manager hoặc Admin
Depends(require_role(Role.MEMBER))             # Từ Member trở lên
```

---

## Security Rules (HYLIST-specific)

```python
# 1. LUÔN filter theo org_id + id (multi-tenancy + chống IDOR)
stmt = select(Task).where(
    Task.org_id == user.org_id,   # Multi-tenancy
    Task.id == task_id,           # IDOR protection
    Task.deleted_at.is_(None),    # Soft delete
)

# 2. Soft delete — KHÔNG xóa thật (cần data để train ML)
await db.execute(
    update(Task)
    .where(Task.id == task_id, Task.org_id == user.org_id)
    .values(deleted_at=datetime.utcnow())
)

# 3. KHÔNG dùng pickle (security risk)
# ❌ model = pickle.load(f)
# ✅ model = onnxruntime.InferenceSession("model.onnx")

# 4. KHÔNG log sensitive data
# ❌ logger.info(f"JWT: {token}")
# ✅ logger.info("user_login", user_id=user.id, ip=request.client.host)

# 5. Rate limiting per endpoint
@limiter.limit("5/minute")   # Sensitive endpoints (login, register)
@limiter.limit("30/minute")  # Standard CRUD
@limiter.limit("60/minute")  # Read-only endpoints
```

---

## AuditLog — BẮT BUỘC (Data cho ML Training)

```python
# models/audit_log.py
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id          = Column(UUID, primary_key=True, default=uuid4)
    org_id      = Column(UUID, nullable=False, index=True)
    user_id     = Column(UUID, nullable=False)
    entity_type = Column(String(50))   # "task", "project", "user"
    entity_id   = Column(UUID, nullable=False)
    action      = Column(String(50))   # "created", "updated", "deleted", "status_changed"
    old_value   = Column(JSONB)        # Trạng thái cũ
    new_value   = Column(JSONB)        # Trạng thái mới
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)

# middleware/audit_log.py — tự động ghi mọi state change
# KHÔNG cần gọi thủ công trong service
```

---

## ML-Ready Schema Fields (Phase 1 — thiết kế ngay từ đầu)

```python
# models/task.py — các fields ML sẽ dùng để train
class Task(Base):
    # Standard fields
    id, org_id, created_by, title, description, status, priority_score

    # Time tracking (target variable cho regression)
    estimated_time    = Column(Float)    # hours — user input
    actual_time       = Column(Float)    # hours — ghi khi DONE

    # ML features — phải collect từ Tuần 1
    assignee_workload    = Column(Float)   # % capacity của assignee lúc assign
    dependency_count     = Column(Integer) # Số task phụ thuộc vào task này
    subtask_count        = Column(Integer)
    revision_count       = Column(Integer) # Số lần bị reopen/reject
    blocked_duration_hrs = Column(Float)   # Thời gian bị block
    context_switch_count = Column(Integer) # Số lần assignee bị interrupt
    deadline_buffer_hrs  = Column(Float)   # Thời gian còn lại trước deadline khi assign

    # NLP output (Phase 3)
    tags              = Column(ARRAY(String))  # ["Bug", "Frontend", "Urgent"]
    nlp_confidence    = Column(Float)          # Confidence của SetFit model

    # Audit
    created_at, updated_at, deleted_at (soft delete), completed_at
```

---

## Observability Pattern (từ Tuần 1)

```python
# Mọi endpoint đều có:
# 1. Sentry error tracking (automatic qua middleware)
# 2. Prometheus metrics
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("hylist_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("hylist_request_duration_seconds", "Request latency", ["endpoint"])

# 3. Structured logging (structlog — KHÔNG dùng print)
import structlog
logger = structlog.get_logger()

# ✅ Structured — searchable trong Grafana Loki
logger.info("task_created", task_id=str(task.id), org_id=str(user.org_id), duration_ms=42)

# ❌ Unstructured — không query được
print(f"Task created: {task.id}")
```

---

## Alembic Migration Rules

```bash
# LUÔN tạo migration sau khi đổi schema
alembic revision --autogenerate -m "add context_switch_count to tasks"
alembic upgrade head

# KHÔNG bao giờ:
# ❌ Sửa migration file đã commit
# ❌ Dùng Base.metadata.create_all() trong production
# ❌ Drop column trực tiếp (dùng soft deprecation trước)
```

---

## Self-Check

```
[ ] Service KHÔNG import Request/Response/HTTPException
[ ] Mọi query filter theo org_id (multi-tenancy)
[ ] Mọi user resource filter theo user.id (IDOR)
[ ] DB session dùng Depends(get_db) — KHÔNG tạo session trong service
[ ] Idempotency key check cho mọi POST/PUT quan trọng
[ ] AuditLog ghi lại state change (qua middleware, không thủ công)
[ ] Input validate bằng Pydantic Field — không validate thủ công
[ ] KHÔNG dùng pickle — dùng ONNX
[ ] KHÔNG log sensitive data (password, token, PII)
[ ] Rate limit đã set cho endpoint
[ ] Alembic migration tạo sau khi đổi schema
[ ] Structured logging với context fields
[ ] KHÔNG có print() debug trong production code
```
