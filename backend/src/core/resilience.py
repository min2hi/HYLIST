"""
Resilience Utilities — Timeout, Retry, Circuit Breaker.

Pattern dung tai: Netflix (Hystrix concept), Google SRE Book, AWS Well-Architected.

Van de khong co resilience:
  - Redis down 3s → SSE bus call treo → API thread bi block
  - ONNX predict chay qua 5s → request queue day → cascade failure
  - Celery broker unavailable → .delay() treo → user request timeout

Giai phap:
  1. Timeout   → moi external call co deadline tuyet doi
  2. Retry     → tu dong retry voi exponential backoff
  3. Circuit Breaker → sau N failures → stop trying → fast-fail immediately

Nguyen tac:
  - Fail fast > hang forever
  - Partial degradation > total outage
  - Every external I/O call can fail
"""

from __future__ import annotations

import asyncio
import builtins
import time
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# ─── Timeout ──────────────────────────────────────────────────────────────────


class TimeoutError(Exception):  # noqa: A001
    """Raised when an operation exceeds its time budget."""


async def with_timeout(  # noqa: UP047
    coro: Coroutine[Any, Any, T],
    seconds: float,
    operation: str = "operation",
) -> T:
    """
    Wrap coroutine voi timeout tuyet doi.
    Raise TimeoutError neu qua han — KHONG hang mai.

    Usage:
        result = await with_timeout(redis.ping(), seconds=2.0, operation="redis_ping")
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except builtins.TimeoutError:
        logger.error(
            "timeout_exceeded",
            operation=operation,
            timeout_seconds=seconds,
        )
        raise TimeoutError(f"{operation} exceeded {seconds}s timeout") from None


# ─── Circuit Breaker ──────────────────────────────────────────────────────────


class CircuitState(StrEnum):
    CLOSED = "closed"  # Binh thuong — cho phep request
    OPEN = "open"  # Dang hu — fast-fail tat ca request
    HALF_OPEN = "half_open"  # Thu lai sau cooldown


class CircuitBreakerError(Exception):  # N818 compliant: Error suffix
    """Raised when circuit breaker is open — fast fail."""


# Alias de backward compat voi code cu
CircuitBreakerOpen = CircuitBreakerError


class CircuitBreaker:
    """
    Circuit Breaker pattern theo Martin Fowler.

    States:
      CLOSED    → request chay binh thuong
      OPEN      → fast-fail sau khi vuot failure_threshold
      HALF_OPEN → sau cooldown_seconds, thu 1 request
                  neu thanh cong → CLOSED
                  neu that bai  → OPEN lai

    Tong cong: giam cascade failures khi dependency down.
    Vi du: ML service down 30s → circuit OPEN → API tra fallback ngay
           thay vi cho tung request bi timeout 5s.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,  # So failures truoc khi OPEN
        success_threshold: int = 2,  # So successes truoc khi CLOSED tu HALF_OPEN
        cooldown_seconds: float = 30.0,  # Thoi gian o OPEN truoc khi thu HALF_OPEN
        timeout_seconds: float = 10.0,  # Timeout cho moi call
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> CircuitState:
        # Kiem tra xem co nen chuyen tu OPEN → HALF_OPEN khong
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time is not None
            and time.monotonic() - self._last_failure_time >= self.cooldown_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info("circuit_breaker_half_open", name=self.name)
        return self._state

    async def call(self, coro: Coroutine[Any, Any, T], operation: str = "") -> T:
        """
        Execute coroutine voi circuit breaker protection.
        Raise CircuitBreakerOpen neu circuit dang OPEN.
        """
        if self.state == CircuitState.OPEN:
            logger.warning(
                "circuit_breaker_open_fast_fail",
                name=self.name,
                operation=operation,
            )
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable, retry after {self.cooldown_seconds}s."
            )

        try:
            result = await with_timeout(coro, self.timeout_seconds, operation or self.name)
            self._on_success()
            return result
        except (TimeoutError, Exception):
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("circuit_breaker_closed", name=self.name)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.error(
                    "circuit_breaker_opened",
                    name=self.name,
                    failures=self._failure_count,
                    cooldown_seconds=self.cooldown_seconds,
                )
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("circuit_breaker_reopened", name=self.name)

    @property
    def metrics(self) -> dict[str, Any]:
        """Expose metrics cho Prometheus / health endpoint."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure_ago": (
                round(time.monotonic() - self._last_failure_time, 1)
                if self._last_failure_time
                else None
            ),
        }


# ─── Retry with Exponential Backoff ───────────────────────────────────────────


async def retry(  # noqa: UP047
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    *,
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    operation: str = "operation",
) -> T:
    """
    Retry async operation voi exponential backoff.

    Khong nen retry:
      - 4xx errors (client error — retry vo ich)
      - Business logic errors
    Nen retry:
      - Network timeouts
      - 5xx (transient server error)
      - Connection reset

    Usage:
        result = await retry(
            lambda: redis_client.ping(),
            max_attempts=3,
            initial_delay=0.5,
            operation="redis_ping",
        )
    """
    delay = initial_delay
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except exceptions as exc:
            last_exc = exc
            if attempt == max_attempts:
                logger.error(
                    "retry_exhausted",
                    operation=operation,
                    attempts=max_attempts,
                    final_error=str(exc),
                )
                break

            logger.warning(
                "retry_attempt",
                operation=operation,
                attempt=attempt,
                max_attempts=max_attempts,
                retry_in=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)

    raise last_exc  # type: ignore[misc]


# ─── Pre-configured Circuit Breakers (Singletons) ─────────────────────────────
# Tao 1 lan, dung toan bo app.
# Tach rieng per-service de khong bi loi 1 service anh huong CB cua service khac.

ml_circuit = CircuitBreaker(
    name="ml_onnx",
    failure_threshold=5,
    cooldown_seconds=30.0,
    timeout_seconds=5.0,  # ONNX inference phai xong trong 5s
)

redis_circuit = CircuitBreaker(
    name="redis",
    failure_threshold=3,
    cooldown_seconds=15.0,
    timeout_seconds=2.0,  # Redis phai respond trong 2s
)

nlp_circuit = CircuitBreaker(
    name="nlp_celery",
    failure_threshold=5,
    cooldown_seconds=60.0,  # NLP worker slow — cho nhieu thoi gian hon
    timeout_seconds=10.0,
)
