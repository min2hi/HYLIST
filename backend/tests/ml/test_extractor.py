"""
Tests cho TaskFeatureExtractor — HYLIST Phase 2.

Nguyên tắc:
    - Test mọi feature logic trong _extract_single()
    - Test cả dict path (serving) lẫn DataFrame path (training)
    - Test edge cases: None, NaN, missing fields
    - Test tags parsing: JSON list, comma-separated, None

Run: pytest backend/tests/ml/test_extractor.py -v
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ml.features.task_extractor import FEATURE_VERSION, TaskFeatureExtractor


@pytest.fixture
def extractor() -> TaskFeatureExtractor:
    return TaskFeatureExtractor()


def make_task(**kwargs) -> dict:
    """Tạo task dict với defaults hợp lệ."""
    base = {
        "title": "Fix login bug",
        "description": "User cannot login with correct credentials",
        "priority_score": 4,
        "deadline": None,
        "assignee_workload": 0.6,
        "revision_count": 2,
        "tags": ["Bug"],
    }
    base.update(kwargs)
    return base


# ── Version ───────────────────────────────────────────────────────────────────


def test_feature_version_defined():
    """FEATURE_VERSION phải được định nghĩa để track model compatibility."""
    assert FEATURE_VERSION == "v1"
    assert TaskFeatureExtractor.VERSION == "v1"


def test_feature_names_count(extractor):
    """Phải có đúng 13 features theo thiết kế."""
    assert len(extractor.FEATURE_NAMES) == 13


# ── Dict path (serving) ───────────────────────────────────────────────────────


class TestDictTransform:

    def test_returns_ndarray_shape(self, extractor):
        """Dict input → np.ndarray shape (1, 13)."""
        task = make_task()
        result = extractor.transform(task)
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 13)

    def test_priority_score_extracted(self, extractor):
        """priority_score được extract đúng vị trí."""
        task = make_task(priority_score=5)
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("priority_score")
        assert result[0, idx] == 5.0

    def test_has_description_true(self, extractor):
        """has_description = 1 nếu có description."""
        task = make_task(description="Some description")
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("has_description")
        assert result[0, idx] == 1.0

    def test_has_description_false(self, extractor):
        """has_description = 0 nếu description rỗng."""
        task = make_task(description="")
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("has_description")
        assert result[0, idx] == 0.0

    def test_has_description_none(self, extractor):
        """has_description = 0 nếu description là None."""
        task = make_task(description=None)
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("has_description")
        assert result[0, idx] == 0.0


# ── Deadline features ─────────────────────────────────────────────────────────


class TestDeadlineFeatures:

    def test_no_deadline(self, extractor):
        """Không có deadline → has_deadline=0, is_overdue=0, buffer=24h default."""
        task = make_task(deadline=None)
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("has_deadline")] == 0.0
        assert result[0, names.index("is_overdue")] == 0.0
        assert result[0, names.index("deadline_buffer_hrs")] == 24.0

    def test_future_deadline_not_overdue(self, extractor):
        """Deadline trong tương lai → is_overdue=0, buffer > 0."""
        future = datetime.now(UTC) + timedelta(hours=48)
        task = make_task(deadline=future)
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("has_deadline")] == 1.0
        assert result[0, names.index("is_overdue")] == 0.0
        assert result[0, names.index("deadline_buffer_hrs")] > 0

    def test_past_deadline_overdue(self, extractor):
        """Deadline đã qua → is_overdue=1, buffer < 0."""
        past = datetime.now(UTC) - timedelta(hours=5)
        task = make_task(deadline=past)
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_overdue")] == 1.0
        assert result[0, names.index("deadline_buffer_hrs")] < 0

    def test_deadline_as_string(self, extractor):
        """Deadline dạng ISO string (từ CSV) phải parse được."""
        future_str = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        task = make_task(deadline=future_str)
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("has_deadline")] == 1.0


# ── Tags parsing ──────────────────────────────────────────────────────────────


class TestTagsParsing:

    def test_tags_list(self, extractor):
        """Tags dạng list (từ DB)."""
        task = make_task(tags=["Bug", "Urgent"])
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_bug")] == 1.0
        assert result[0, names.index("is_urgent")] == 1.0
        assert result[0, names.index("is_feature")] == 0.0

    def test_tags_comma_string(self, extractor):
        """Tags dạng comma-separated string (từ CSV mock data)."""
        task = make_task(tags="Feature,Research")
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_feature")] == 1.0
        assert result[0, names.index("is_research")] == 1.0
        assert result[0, names.index("is_bug")] == 0.0

    def test_tags_json_string(self, extractor):
        """Tags dạng JSON string (khi serialize từ DB)."""
        task = make_task(tags='["Bug", "Feature"]')
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_bug")] == 1.0
        assert result[0, names.index("is_feature")] == 1.0

    def test_tags_none(self, extractor):
        """Không có tags → tất cả is_X = 0."""
        task = make_task(tags=None)
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_bug")] == 0.0
        assert result[0, names.index("is_feature")] == 0.0
        assert result[0, names.index("is_urgent")] == 0.0
        assert result[0, names.index("is_research")] == 0.0

    def test_tags_case_insensitive(self, extractor):
        """Tags parsing case-insensitive."""
        task = make_task(tags=["BUG", "URGENT"])
        result = extractor.transform(task)
        names = extractor.FEATURE_NAMES

        assert result[0, names.index("is_bug")] == 1.0
        assert result[0, names.index("is_urgent")] == 1.0


# ── Assignee workload ─────────────────────────────────────────────────────────


class TestAssigneeWorkload:

    def test_workload_extracted(self, extractor):
        """assignee_workload được extract đúng."""
        task = make_task(assignee_workload=0.75)
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("assignee_workload")
        assert abs(result[0, idx] - 0.75) < 0.001

    def test_workload_none_uses_default(self, extractor):
        """Thiếu workload → dùng default 0.5."""
        task = make_task(assignee_workload=None)
        result = extractor.transform(task)
        idx = extractor.FEATURE_NAMES.index("assignee_workload")
        assert result[0, idx] == 0.5


# ── DataFrame path (training) ─────────────────────────────────────────────────


class TestDataFrameTransform:

    def test_returns_dataframe(self, extractor):
        """DataFrame input → DataFrame output."""
        df = pd.DataFrame([make_task(), make_task(priority_score=2)])
        result = extractor.transform(df)
        assert isinstance(result, pd.DataFrame)
        assert result.shape == (2, 13)

    def test_column_order_matches_feature_names(self, extractor):
        """Columns phải đúng thứ tự FEATURE_NAMES — quan trọng cho model."""
        df = pd.DataFrame([make_task()])
        result = extractor.transform(df)
        assert list(result.columns) == extractor.FEATURE_NAMES

    def test_batch_consistency_with_single(self, extractor):
        """
        Kết quả batch (DataFrame) phải giống với single (dict) cho cùng 1 row.
        Đây là parity test cơ bản.
        """
        task = make_task(priority_score=5, assignee_workload=0.8)
        single_result = extractor.transform(task)

        df = pd.DataFrame([task])
        batch_result = extractor.transform(df)

        np.testing.assert_array_almost_equal(
            single_result[0],
            batch_result.values[0],
            decimal=5,
        )


# ── Validate input ────────────────────────────────────────────────────────────


class TestValidateInput:

    def test_no_warnings_for_complete_input(self, extractor):
        """Input đầy đủ → không có warnings."""
        task = make_task()
        warnings = extractor.validate_input(task)
        assert len(warnings) == 0

    def test_warning_missing_title(self, extractor):
        """Thiếu title → có warning."""
        task = make_task(title=None)
        warnings = extractor.validate_input(task)
        assert any("title" in w for w in warnings)

    def test_warning_missing_workload_with_assignee(self, extractor):
        """Có assignee_id nhưng không có workload → warning."""
        task = make_task(assignee_workload=None)
        task["assignee_id"] = "some-uuid"
        warnings = extractor.validate_input(task)
        assert any("workload" in w for w in warnings)


# ── Type error ────────────────────────────────────────────────────────────────


def test_invalid_input_type_raises(extractor):
    """Input không phải dict hay DataFrame → TypeError."""
    with pytest.raises(TypeError):
        extractor.transform([1, 2, 3])
