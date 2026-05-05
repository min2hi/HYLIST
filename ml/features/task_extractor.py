"""
Feature Extractor cho Task (Phase 2).
Shared cho cả quá trình Training (từ CSV/Pandas) và Serving (từ Pydantic Model/FastAPI).
Giúp chống Training-Serving Skew.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd


class TaskFeatureExtractor:
    """
    Extract features từ Task raw data.
    Input có thể là 1 Dict (serving) hoặc 1 DataFrame (training).
    Output là Numpy Array (serving) hoặc DataFrame (training).
    """

    # Các feature bắt buộc phải có cho mô hình XGBoost
    FEATURE_NAMES = [
        "priority_score",
        "has_description",
        "description_length",
        "title_length",
        "is_bug",
        "is_feature",
        "is_urgent",
        "is_research",
        "deadline_buffer_hrs",
    ]

    def _extract_single(self, row: Dict[str, Any]) -> Dict[str, float]:
        """Extract features từ 1 dòng dữ liệu dạng dict."""
        features = {}

        # 1. Basic metrics
        features["priority_score"] = float(row.get("priority_score", 3.0))
        
        # 2. Text metrics
        desc = str(row.get("description", "")) if pd.notna(row.get("description")) else ""
        title = str(row.get("title", "")) if pd.notna(row.get("title")) else ""
        
        features["has_description"] = 1.0 if len(desc.strip()) > 0 else 0.0
        features["description_length"] = float(len(desc.split()))
        features["title_length"] = float(len(title.split()))

        # 3. Tags (One-hot encoding)
        tags_str = str(row.get("tags", "")) if pd.notna(row.get("tags")) else ""
        tags = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
        
        features["is_bug"] = 1.0 if "bug" in tags else 0.0
        features["is_feature"] = 1.0 if "feature" in tags else 0.0
        features["is_urgent"] = 1.0 if "urgent" in tags else 0.0
        features["is_research"] = 1.0 if "research" in tags else 0.0

        # 4. Time features
        deadline_str = row.get("deadline")
        created_str = row.get("created_at")
        
        if pd.notna(deadline_str) and pd.notna(created_str):
            try:
                deadline = pd.to_datetime(deadline_str)
                created = pd.to_datetime(created_str)
                buffer = (deadline - created).total_seconds() / 3600.0
                features["deadline_buffer_hrs"] = float(buffer)
            except Exception:
                features["deadline_buffer_hrs"] = 24.0 # default 1 day buffer
        else:
            features["deadline_buffer_hrs"] = 24.0

        return features

    def fit(self, X=None, y=None):
        """Tương thích với scikit-learn Pipeline."""
        return self

    def transform(self, data: pd.DataFrame | Dict[str, Any]) -> pd.DataFrame | np.ndarray:
        """
        Transform raw data thành features.
        Nếu input là DataFrame -> Output DataFrame.
        Nếu input là Dict -> Output 2D Numpy Array (cho inference).
        """
        if isinstance(data, pd.DataFrame):
            # Xử lý theo batch
            records = data.to_dict("records")
            features_list = [self._extract_single(row) for row in records]
            df_features = pd.DataFrame(features_list)
            # Ensure correct column order
            return df_features[self.FEATURE_NAMES]
            
        elif isinstance(data, dict):
            # Xử lý 1 sample
            features = self._extract_single(data)
            # Ensure correct column order
            arr = np.array([[features[name] for name in self.FEATURE_NAMES]])
            return arr
            
        else:
            raise ValueError("Input data phải là pandas DataFrame hoặc Dictionary")

    def get_feature_names(self) -> list[str]:
        return self.FEATURE_NAMES
