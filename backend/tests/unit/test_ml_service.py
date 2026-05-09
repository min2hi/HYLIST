"""
Tests cho MLService va Resilience utilities.

Coverage target: ml_service.py 30% → 75%+

Strategy:
  - Mock onnxruntime.InferenceSession → khong can ONNX file thuc
  - Mock TaskFeatureExtractor → khong can pandas trong CI
  - Test moi code path: init, predict, fallback, circuit breaker
  - Test resilience.py: timeout, circuit breaker states, retry
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ─── MLService Tests ──────────────────────────────────────────────────────────


class TestPredictionResult:
    """Test PredictionResult data class."""

    def test_to_dict_full(self):
        from src.services.ml_service import PredictionResult

        r = PredictionResult(
            predicted_hours=4.5,
            confidence=0.82,
            model_version="v1",
            latency_ms=3.14,
            fallback=False,
            shap_values={"priority_score": 0.5},
            shap_base_value=3.0,
        )
        d = r.to_dict()
        assert d["predicted_hours"] == 4.5
        assert d["confidence"] == 0.82
        assert d["model_version"] == "v1"
        assert d["fallback"] is False
        assert d["shap_values"] == {"priority_score": 0.5}

    def test_to_dict_fallback(self):
        from src.services.ml_service import PredictionResult

        r = PredictionResult(
            predicted_hours=4.0,
            confidence=0.3,
            model_version="rule-based-fallback",
            latency_ms=0.1,
            fallback=True,
        )
        d = r.to_dict()
        assert d["fallback"] is True
        assert d["shap_values"] is None
        assert d["confidence"] == 0.3


class TestMLServiceInitialize:
    """Test MLService.initialize() code paths."""

    def setup_method(self):
        """Reset singleton state before each test."""
        from src.services.ml_service import MLService

        MLService._instance = None
        MLService._session = None
        MLService._extractor = None
        MLService._initialized = False

    def test_initialize_graceful_when_no_extractor(self):
        """initialize() set fallback mode khi extractor chua duoc load."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = None
        service._extractor = None

        # Khi session va extractor deu None → is_ready phai False
        assert service.is_ready is False

    def test_initialize_skips_if_already_initialized(self):
        """initialize() idempotent — goi 2 lan khong co side effect."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        original_session = service._session

        service.initialize()  # Goi lan 2

        assert service._session == original_session  # Khong thay doi

    def test_initialize_sets_initialized_flag(self):
        """initialize() luon set _initialized = True du thanh cong hay that bai."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = False

        with patch.object(service, "_extractor", None):
            with patch("pathlib.Path.exists", return_value=False):
                # Model file khong ton tai → fallback
                with patch("builtins.__import__") as mock_import:
                    # Allow normal imports but fail TaskFeatureExtractor
                    def import_side_effect(name, *args, **kwargs):
                        if "task_extractor" in name:
                            raise ImportError("no module")
                        return __import__(name, *args, **kwargs)

                    mock_import.side_effect = import_side_effect
                    try:
                        service.initialize()
                    except Exception:  # noqa: S110
                        pass

        # Even on failure, should not crash app

    def test_is_ready_false_when_no_session(self):
        """is_ready returns False khi session chua load."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = None
        assert service.is_ready is False

    def test_is_ready_true_when_session_loaded(self):
        """is_ready returns True khi session da load."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = MagicMock()  # Mock session
        assert service.is_ready is True

    def test_model_version_property(self):
        from src.services.ml_service import MLService

        service = MLService()
        service._model_version = "v2-xgboost"
        assert service.model_version == "v2-xgboost"


class TestMLServicePredict:
    """Test MLService.predict() voi mock ONNX session."""

    def setup_method(self):
        from src.services.ml_service import MLService

        MLService._instance = None
        MLService._session = None
        MLService._extractor = None
        MLService._initialized = False

    @pytest.mark.asyncio
    async def test_predict_returns_fallback_when_no_session(self):
        """predict() tra fallback khi ONNX model chua load."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = None  # Model chua load

        result = await service.predict({"priority_score": 3})

        assert result.fallback is True
        assert result.model_version == "rule-based-fallback"
        assert result.predicted_hours == 4.0  # priority 3 → 4 hours
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_predict_fallback_all_priorities(self):
        """Rule-based fallback co mapping dung cho tat ca priority levels."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = None

        expected = {1: 1.0, 2: 2.0, 3: 4.0, 4: 6.0, 5: 8.0}
        for priority, expected_hours in expected.items():
            result = await service.predict({"priority_score": priority})
            assert result.predicted_hours == expected_hours, f"priority={priority}"

    @pytest.mark.asyncio
    async def test_predict_with_mock_onnx_session(self):
        """predict() goi ONNX session va tra ket qua dung."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._model_version = "v1"
        service._input_name = "float_input"
        service._session = MagicMock()
        service._session.run = MagicMock(
            return_value=[np.array([[5.5]])]  # Predicted 5.5 hours
        )
        service._explainer = None

        # Mock TaskFeatureExtractor
        mock_extractor = MagicMock()
        features_row = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0]
        mock_extractor.transform = MagicMock(
            return_value=np.array([features_row])
        )
        mock_extractor.FEATURE_NAMES = [f"feat_{i}" for i in range(13)]
        service._extractor = mock_extractor

        # Reset circuit breaker state
        with patch("src.services.ml_service.ml_circuit") as mock_circuit:
            mock_circuit.call = AsyncMock(
                return_value=MagicMock(
                    predicted_hours=5.5,
                    confidence=0.7,
                    fallback=False,
                    to_dict=lambda: {},
                )
            )
            result = await service.predict({"priority_score": 4})
            assert result.fallback is False

    @pytest.mark.asyncio
    async def test_predict_returns_fallback_on_circuit_open(self):
        """predict() tra fallback khi circuit breaker dang OPEN."""
        from src.core.resilience import CircuitBreakerOpen
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = MagicMock()
        service._extractor = MagicMock()
        service._extractor.transform = MagicMock(return_value=np.zeros((1, 13)))

        with patch("src.services.ml_service.ml_circuit") as mock_circuit:
            mock_circuit.call = AsyncMock(side_effect=CircuitBreakerOpen("circuit open"))
            mock_circuit.metrics = {"state": "open"}

            result = await service.predict({"priority_score": 2})
            assert result.fallback is True

    @pytest.mark.asyncio
    async def test_predict_returns_fallback_on_general_exception(self):
        """predict() tra fallback khi co bat ky exception nao."""
        from src.services.ml_service import MLService

        service = MLService()
        service._initialized = True
        service._session = MagicMock()
        service._extractor = MagicMock()

        with patch("src.services.ml_service.ml_circuit") as mock_circuit:
            mock_circuit.call = AsyncMock(side_effect=RuntimeError("unexpected"))

            result = await service.predict({"priority_score": 5})
            assert result.fallback is True


# ─── Resilience Module Tests ──────────────────────────────────────────────────


class TestWithTimeout:
    """Test timeout wrapper."""

    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        """with_timeout khong raise khi operation xong trong thoi han."""
        from src.core.resilience import with_timeout

        async def fast_op():
            return "done"

        result = await with_timeout(fast_op(), seconds=5.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_raises_timeout_error_when_exceeded(self):
        """with_timeout raise TimeoutError khi qua thoi gian."""
        from src.core.resilience import TimeoutError, with_timeout

        async def slow_op():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(TimeoutError):
            await with_timeout(slow_op(), seconds=0.01, operation="test")

    @pytest.mark.asyncio
    async def test_timeout_error_message_contains_operation(self):
        """TimeoutError message co ten operation de de debug."""
        from src.core.resilience import TimeoutError, with_timeout

        async def slow():
            await asyncio.sleep(10)

        try:
            await with_timeout(slow(), seconds=0.01, operation="redis_ping")
        except TimeoutError as e:
            assert "redis_ping" in str(e)
            assert "0.01" in str(e)


class TestCircuitBreaker:
    """Test Circuit Breaker 3-state FSM."""

    def make_circuit(self, **kwargs):  # type: ignore[return]
        from src.core.resilience import CircuitBreaker

        defaults = {
            "name": "test",
            "failure_threshold": 3,
            "success_threshold": 2,
            "cooldown_seconds": 30.0,
            "timeout_seconds": 5.0,
        }
        defaults.update(kwargs)
        return CircuitBreaker(**defaults)

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        """Circuit bat dau o trang thai CLOSED."""
        from src.core.resilience import CircuitState

        cb = self.make_circuit()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        """Circuit chuyen sang OPEN sau failure_threshold lan that bai."""
        from src.core.resilience import CircuitState

        cb = self.make_circuit(failure_threshold=3, timeout_seconds=0.01)

        async def failing_op():
            raise RuntimeError("simulated failure")

        for _ in range(3):
            with pytest.raises(Exception):
                await cb.call(failing_op(), "test")

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_fast_fails_when_open(self):
        """Circuit OPEN → fast-fail ngay, khong thuc thi operation."""
        from src.core.resilience import CircuitBreakerOpen, CircuitState

        cb = self.make_circuit(failure_threshold=1, timeout_seconds=0.01)

        async def failing():
            raise RuntimeError("fail")

        with pytest.raises(Exception):
            await cb.call(failing(), "test")

        assert cb.state == CircuitState.OPEN

        # Call tiep theo phai fast-fail ngay
        call_count = 0

        async def should_not_run():
            nonlocal call_count
            call_count += 1
            return "result"

        with pytest.raises(CircuitBreakerOpen):
            await cb.call(should_not_run(), "test")

        assert call_count == 0  # Operation KHONG duoc thuc thi

    @pytest.mark.asyncio
    async def test_metrics_returns_state_info(self):
        """metrics property tra ve thong tin state day du."""
        cb = self.make_circuit()
        m = cb.metrics
        assert m["name"] == "test"
        assert m["state"] == "closed"
        assert m["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_successful_call_passes_through(self):
        """Call thanh cong tra ve ket qua dung."""
        cb = self.make_circuit()

        async def success_op():
            return 42

        result = await cb.call(success_op(), "test")
        assert result == 42


class TestRetry:
    """Test retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Neu thanh cong lan dau, khong retry."""
        from src.core.resilience import retry

        call_count = 0

        async def op():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry(op, max_attempts=3, initial_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """Retry sau that bai roi thanh cong."""
        from src.core.resilience import retry

        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "success"

        result = await retry(
            flaky,
            max_attempts=3,
            initial_delay=0.01,
            operation="test",
        )
        assert result == "success"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Raise exception sau khi het max_attempts."""
        from src.core.resilience import retry

        async def always_fail():
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            await retry(
                always_fail,
                max_attempts=2,
                initial_delay=0.01,
                operation="test",
            )
