# Agent & LLM Workflow Rules

> Stack: LangChain + Celery + Celery Beat + Redis + Microsoft Presidio

## Nguyên Tắc Cốt Lõi

> **An toàn trước tiên:** Mọi LLM output PHẢI qua AgentOutputValidator trước khi lưu DB hoặc hiển thị user. Mọi LLM call PHẢI kiểm tra budget trước khi thực thi.

## Budget Guard Pattern (BẮT BUỘC — kiểm tra TRƯỚC mọi LLM call)

```python
# backend/src/workers/budget_guard.py
class LLMBudgetGuard:
    DAILY_LIMIT_USD = 10.0

    async def can_execute(self, user_id: str) -> bool:
        key = f"llm_spend:{user_id}:{date.today()}"
        today_spend = float(await redis.get(key) or 0)
        return today_spend < self.DAILY_LIMIT_USD

    async def record_spend(self, user_id: str, cost_usd: float):
        key = f"llm_spend:{user_id}:{date.today()}"
        await redis.incrbyfloat(key, cost_usd)
        await redis.expire(key, 86400)  # Reset sau 24h

budget_guard = LLMBudgetGuard()

# Dùng trong mọi Celery task gọi LLM:
@celery.task(bind=True)
async def research_agent_task(self, task_id: str, user_id: str):
    if not await budget_guard.can_execute(user_id):
        logger.warning("budget_exceeded", user_id=user_id, task_id=task_id)
        self.apply_async(args=[task_id, user_id], countdown=86400)  # Retry tomorrow
        return
    # ... proceed with LLM call
```

## Agent Output Validator (BẮT BUỘC — sau mọi LLM output)

```python
# backend/src/workers/output_validator.py
from presidio_analyzer import AnalyzerEngine

analyzer = AnalyzerEngine()

class AgentOutputValidator:
    MAX_LENGTH = 2000

    def validate(self, output: str) -> tuple[bool, str]:
        # 1. Length check
        if len(output) > self.MAX_LENGTH:
            return False, "Output quá dài"

        # 2. PII detection
        results = analyzer.analyze(text=output, language="en")
        if results:
            return False, f"Phát hiện PII: {[r.entity_type for r in results]}"

        # 3. Secret pattern detection
        secret_patterns = [r"\bsk-[a-zA-Z0-9]{20,}\b", r"\bghp_[a-zA-Z0-9]{36}\b"]
        for pattern in secret_patterns:
            if re.search(pattern, output):
                return False, "Phát hiện secret/token trong output"

        return True, output

validator = AgentOutputValidator()
```

## Tool Sandbox Pattern (BẮT BUỘC — mọi agent tool)

```python
# backend/src/workers/tools/web_crawler.py
from langchain.tools import BaseTool
from urllib.parse import urlparse

ALLOWED_DOMAINS = frozenset([
    "wikipedia.org", "arxiv.org", "docs.python.org",
    "fastapi.tiangolo.com", "docs.sqlalchemy.org",
])

class SafeWebCrawler(BaseTool):
    name = "web_crawler"
    description = "Crawl nội dung từ các domain được phép"

    def _run(self, url: str) -> str:
        domain = urlparse(url).netloc.replace("www.", "")
        if domain not in ALLOWED_DOMAINS:
            raise ToolException(f"Domain '{domain}' không được phép. Chỉ cho phép: {ALLOWED_DOMAINS}")

        response = httpx.get(url, timeout=10, follow_redirects=True)
        return response.text[:5000]  # Giới hạn response size
```

## Human-in-the-Loop (HITL) Pattern

```python
# backend/src/models/agent_action.py
class AgentAction(Base):
    __tablename__ = "agent_actions"
    status = Column(Enum("pending_review", "approved", "rejected", "auto_applied"))
    proposed_content = Column(Text)
    confidence_score = Column(Float)
    task_id = Column(UUID, ForeignKey("tasks.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

# backend/src/workers/agent_pipeline.py
async def commit_agent_result(task_id: str, result: str, confidence: float):
    is_valid, validated = validator.validate(result)
    if not is_valid:
        logger.warning("agent_output_rejected", reason=validated, task_id=task_id)
        return

    if confidence >= 0.95:
        # High confidence → auto apply
        await apply_comment_to_task(task_id, validated)
        await log_agent_action(task_id, "auto_applied", confidence, validated)
    else:
        # Low confidence → wait for human review
        await create_pending_review(task_id, validated, confidence)
        await notify_assignee(task_id, "Agent đề xuất nội dung, cần bạn review")
```

## Semantic Cache Pattern (tiết kiệm 40–60% LLM costs)

```python
# backend/src/core/llm_cache.py
from langchain.cache import RedisSemanticCache
from langchain.embeddings import OpenAIEmbeddings
import langchain

def setup_semantic_cache():
    langchain.llm_cache = RedisSemanticCache(
        redis_url=settings.REDIS_URL,
        embedding=OpenAIEmbeddings(),
        score_threshold=0.95,   # Query giống 95% → dùng cache
    )

# Gọi khi khởi động app
setup_semantic_cache()
```

## Celery Task Structure (cho Agent jobs)

```python
# backend/src/workers/research_task.py
@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="agent",              # Queue riêng cho agent jobs
    time_limit=300,             # Hard timeout 5 phút
    soft_time_limit=240,        # Soft timeout 4 phút (raise SoftTimeLimitExceeded)
)
def run_research_agent(self, task_id: str, user_id: str, task_description: str):
    try:
        if not asyncio.run(budget_guard.can_execute(user_id)):
            self.apply_async(args=[task_id, user_id, task_description], countdown=86400)
            return

        agent = create_research_agent()
        result = agent.run(f"Research và tóm tắt thông tin về: {task_description}")
        confidence = calculate_confidence(result)

        asyncio.run(commit_agent_result(task_id, result, confidence))

    except SoftTimeLimitExceeded:
        logger.warning("agent_timeout", task_id=task_id)
        asyncio.run(create_pending_review(task_id, "Agent timeout — cần xử lý thủ công", 0.0))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)
```

## Dead Letter Queue Handling

```python
# Tin nhắn fail sau max_retries → DLQ
@celery.task
def handle_dead_letter(task_id: str, error: str, original_task: str):
    logger.error("agent_dlq", task_id=task_id, error=error)
    asyncio.run(notify_admin(f"Agent task {task_id} thất bại: {error}"))
    asyncio.run(create_pending_review(task_id, f"Auto-failed: {error}", 0.0))
```

## Self-Check

```
[ ] Mọi LLM call có kiểm tra budget_guard.can_execute() trước
[ ] Mọi LLM output đi qua validator.validate() trước khi lưu DB
[ ] Mọi tool kế thừa SafeBaseTool và có domain/action allowlist
[ ] HITL: confidence < 0.95 → pending_review, không auto-apply
[ ] Celery task có time_limit và soft_time_limit
[ ] Semantic cache đã setup khi khởi động
[ ] Dead Letter Queue handler đã registered
[ ] Không log LLM output thô (có thể chứa PII)
```
