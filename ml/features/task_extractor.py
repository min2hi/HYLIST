"""
TaskFeatureExtractor — HYLIST Phase 2 ML Engine.

⚠️  FILE CỰC KỲ NHẠY CẢM (xem MEMORY.md).
    Dùng chung cho CẢ TRAINING lẫn SERVING.
    Sửa logic ở đây → PHẢI chạy parity test.
    Sửa FEATURE_NAMES → train lại model từ đầu.

Luồng:
    Training:  DataFrame (từ CSV)  → transform() → DataFrame  → XGBoost.fit()
    Serving:   dict (từ API/DB)    → transform() → np.ndarray → ONNX.run()

Phòng tránh Training-Serving Skew:
    - Mọi logic transform phải đi qua _extract_single()
    - Không được dùng inline calculation ở nơi khác
    - Parity test: tests/ml/test_parity.py phải PASS 100%
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

# ── Version ──────────────────────────────────────────────────────────────────
# Tăng version khi thêm/xóa/đổi thứ tự feature.
# Model phải được train lại khi version thay đổi.
FEATURE_VERSION = "v1"

# Default values cho missing features (dùng median của training data)
_DEFAULTS: dict[str, float] = {
    "priority_score": 3.0,
    "has_description": 0.0,
    "description_length": 0.0,
    "title_length": 3.0,
    "has_deadline": 0.0,
    "deadline_buffer_hrs": 24.0,   # 1 ngày — conservative default
    "is_overdue": 0.0,
    "assignee_workload": 0.5,      # 50% workload — unknown default
    "revision_count": 0.0,
    "is_bug": 0.0,
    "is_feature": 0.0,
    "is_urgent": 0.0,
    "is_research": 0.0,
}


class TaskFeatureExtractor:
    """
    Extract và transform raw task data thành ML features.

    Input có thể là:
        - dict:            1 sample (API serving path)
        - pd.DataFrame:    nhiều samples (training path)

    Output:
        - np.ndarray shape (1, n_features):       khi input là dict
        - pd.DataFrame shape (n, n_features):     khi input là DataFrame
    """

    # Thứ tự FEATURE_NAMES phải KHÔNG ĐỔI sau khi train model.
    # Thêm feature mới → thêm vào CUỐI + tăng FEATURE_VERSION.
    FEATURE_NAMES: list[str] = [
        # ── Task content ────────────────────────────────────────
        "priority_score",        # int 1-5, user-defined
        "has_description",       # binary: mô tả hay không
        "description_length",    # số từ trong description
        "title_length",          # số từ trong title
        # ── Time / Deadline ──────────────────────────────────────
        "has_deadline",          # binary: có deadline hay không
        "deadline_buffer_hrs",   # giờ còn lại đến deadline (âm = overdue)
        "is_overdue",            # binary: đã quá deadline chưa
        # ── Assignee ────────────────────────────────────────────
        "assignee_workload",     # 0.0-1.0: current_tasks / max_capacity
        # ── History / ML signals ─────────────────────────────────
        "revision_count",        # số lần edit task (signal: task phức tạp)
        # ── Tags (one-hot, Phase 3 sẽ dùng NLP để fill) ─────────
        "is_bug",
        "is_feature",
        "is_urgent",
        "is_research",
    ]

    VERSION = FEATURE_VERSION

    # ── Public API ────────────────────────────────────────────────────────────

    def fit(self, X: Any = None, y: Any = None) -> "TaskFeatureExtractor":
        """Tương thích với scikit-learn Pipeline (stateless extractor)."""
        return self

    def transform(
        self, data: pd.DataFrame | dict[str, Any]
    ) -> pd.DataFrame | np.ndarray:
        """
        Transform raw data → features.

        Args:
            data: DataFrame (training) hoặc dict (serving)

        Returns:
            DataFrame nếu input là DataFrame.
            np.ndarray shape (1, n_features) nếu input là dict.
        """
        if isinstance(data, pd.DataFrame):
            records = data.to_dict("records")
            features_list = [self._extract_single(row) for row in records]
            df = pd.DataFrame(features_list)
            return df[self.FEATURE_NAMES]  # Đảm bảo đúng thứ tự

        if isinstance(data, dict):
            features = self._extract_single(data)
            arr = np.array([[features[name] for name in self.FEATURE_NAMES]])
            return arr  # shape (1, 13)

        raise TypeError(
            f"Input phải là pd.DataFrame hoặc dict, nhận được: {type(data)}"
        )

    def get_feature_names(self) -> list[str]:
        """Trả về tên features theo đúng thứ tự model dùng."""
        return list(self.FEATURE_NAMES)

    def validate_input(self, row: dict[str, Any]) -> list[str]:
        """
        Kiểm tra input có đủ thông tin để extract không.
        Trả về danh sách warnings (không raise — dùng default thay thế).

        Returns:
            list[str]: danh sách cảnh báo, rỗng nếu input hoàn chỉnh.
        """
        warnings: list[str] = []
        if not row.get("title"):
            warnings.append("title bị thiếu — dùng default title_length=3")
        if row.get("priority_score") is None:
            warnings.append("priority_score bị thiếu — dùng default 3")
        if row.get("assignee_id") and row.get("assignee_workload") is None:
            warnings.append("assignee_workload bị thiếu dù có assignee — dùng default 0.5")
        return warnings

    # ── Internal ──────────────────────────────────────────────────────────────

    def _extract_single(self, row: dict[str, Any]) -> dict[str, float]:
        """
        Extract features từ 1 dòng data (dict).
        Luôn trả về đầy đủ FEATURE_NAMES — dùng _DEFAULTS nếu thiếu.

        Đây là hàm DUY NHẤT được phép chứa feature logic.
        """
        features: dict[str, float] = {}

        # ── 1. Priority ───────────────────────────────────────────────────────
        features["priority_score"] = float(
            row.get("priority_score") or _DEFAULTS["priority_score"]
        )

        # ── 2. Text metrics ───────────────────────────────────────────────────
        desc = self._safe_str(row.get("description"))
        title = self._safe_str(row.get("title"))

        features["has_description"] = 1.0 if desc.strip() else 0.0
        features["description_length"] = float(len(desc.split()))
        features["title_length"] = float(len(title.split())) if title.strip() else _DEFAULTS["title_length"]

        # ── 3. Deadline features ──────────────────────────────────────────────
        deadline_dt = self._parse_datetime(row.get("deadline"))
        now_utc = datetime.now(UTC)

        if deadline_dt is not None:
            # Normalize timezone: deadline có thể naive (từ CSV) hoặc aware (từ DB)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=UTC)

            features["has_deadline"] = 1.0
            buffer_hrs = (deadline_dt - now_utc).total_seconds() / 3600.0
            features["deadline_buffer_hrs"] = float(buffer_hrs)
            features["is_overdue"] = 1.0 if buffer_hrs < 0 else 0.0
        else:
            features["has_deadline"] = 0.0
            features["deadline_buffer_hrs"] = _DEFAULTS["deadline_buffer_hrs"]
            features["is_overdue"] = 0.0

        # ── 4. Assignee workload ──────────────────────────────────────────────
        # Đã được pre-computed và lưu vào task khi tạo (task_service.py)
        # Nếu không có (CSV training data) → dùng default 0.5
        workload = row.get("assignee_workload")
        if workload is not None:
            features["assignee_workload"] = float(workload)
        else:
            features["assignee_workload"] = _DEFAULTS["assignee_workload"]

        # ── 5. History signals ────────────────────────────────────────────────
        features["revision_count"] = float(row.get("revision_count") or 0)

        # ── 6. Tags (one-hot) ─────────────────────────────────────────────────
        # FIX: Support cả JSON list (từ DB) lẫn comma-separated string (từ CSV)
        tags = self._parse_tags(row.get("tags"))

        features["is_bug"] = 1.0 if "bug" in tags else 0.0
        features["is_feature"] = 1.0 if "feature" in tags else 0.0
        features["is_urgent"] = 1.0 if "urgent" in tags else 0.0
        features["is_research"] = 1.0 if "research" in tags else 0.0

        return features

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_str(value: Any) -> str:
        """Chuyển đổi value về string, handle None và NaN."""
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse datetime từ nhiều format khác nhau."""
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, datetime):
            return value
        try:
            return pd.to_datetime(value).to_pydatetime()
        except Exception:
            return None

    @staticmethod
    def _parse_tags(value: Any) -> set[str]:
        """
        Parse tags từ nhiều format:
          - list[str]: ["Bug", "Feature"]        ← từ DB (JSON column)
          - str JSON:  '["Bug", "Feature"]'      ← từ DB serialized
          - str CSV:   "Bug,Feature,Urgent"       ← từ CSV training data
          - None / NaN                             ← không có tags
        """
        if value is None:
            return set()
        try:
            if pd.isna(value):
                return set()
        except (TypeError, ValueError):
            pass

        # Already a list (từ DB ORM)
        if isinstance(value, list):
            return {str(t).strip().lower() for t in value if t}

        value_str = str(value).strip()

        # JSON string: '["Bug", "Feature"]'
        if value_str.startswith("["):
            try:
                parsed = json.loads(value_str)
                if isinstance(parsed, list):
                    return {str(t).strip().lower() for t in parsed if t}
            except json.JSONDecodeError:
                pass

        # Comma-separated: "Bug,Feature,Urgent"
        return {t.strip().lower() for t in value_str.split(",") if t.strip()}
