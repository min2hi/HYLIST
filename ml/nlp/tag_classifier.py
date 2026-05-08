"""
TagClassifier — Wrapper cho SetFit inference (Phase 3).
Sử dụng mô hình SetFit đã train để tự động phân loại task.
"""

from typing import Any
import structlog
import os
from pathlib import Path

logger = structlog.get_logger(__name__)

# HuggingFace Hub repo name for the fine-tuned model (placeholder for MVP)
# In production, this would be pulled from DVC or HF Hub
_HF_MODEL_NAME = "sentence-transformers/paraphrase-MiniLM-L3-v2"
_SUPPORTED_TAGS = ["Bug", "Feature", "Urgent", "Research"]

class TagPrediction:
    def __init__(self, tag: str, confidence: float):
        self.tag = tag
        self.confidence = confidence


class TagClassifier:
    """Wrapper cho SetFit Model."""
    
    _instance = None

    def __new__(cls) -> "TagClassifier":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._model = None
        return cls._instance

    def initialize(self) -> None:
        if self._initialized:
            return

        try:
            from setfit import SetFitModel
            
            logger.info("nlp_model_loading", model_name=_HF_MODEL_NAME)
            # Use local path if we have a trained model, otherwise pull base model from HF
            _repo_root = Path(__file__).parent.parent.parent
            _local_model_path = _repo_root / "ml" / "nlp" / "models" / "setfit_tagger"
            
            if _local_model_path.exists():
                logger.info("nlp_model_using_local", path=str(_local_model_path))
                self._model = SetFitModel.from_pretrained(str(_local_model_path))
            else:
                logger.info("nlp_model_using_pretrained", name=_HF_MODEL_NAME)
                self._model = SetFitModel.from_pretrained(_HF_MODEL_NAME)
                
            self._initialized = True
            logger.info("nlp_model_initialized_success")
            
        except Exception as e:
            logger.error("nlp_model_init_failed", error=str(e))
            self._initialized = True # Mark as initialized to prevent constant retries, will use fallback
            
    def predict(self, text: str) -> list[TagPrediction]:
        """
        Dự đoán tag cho văn bản (title + description).
        
        Args:
            text: Văn bản cần phân loại
            
        Returns:
            Danh sách TagPrediction (có thể rỗng nếu model fail)
        """
        if not self._initialized:
            self.initialize()
            
        if self._model is None:
            return [] # Fallback
            
        try:
            import torch
            
            # Predict
            probs = self._model.predict_proba([text])[0]
            
            # If the model is just the base model (not fine-tuned), probs might not map to our classes
            # In a real scenario, SetFitModel trained on our classes returns probs for those classes.
            # We assume model returns a tensor of probabilities for our _SUPPORTED_TAGS.
            
            if len(probs) != len(_SUPPORTED_TAGS):
                logger.warning("nlp_model_untrained_probs", msg="Model is likely not fine-tuned yet, returning empty.")
                return []
                
            # Get top prediction
            top_class_idx = int(torch.argmax(probs))
            confidence = float(probs[top_class_idx])
            tag = _SUPPORTED_TAGS[top_class_idx]
            
            return [TagPrediction(tag=tag, confidence=confidence)]
            
        except Exception as e:
            logger.error("nlp_predict_error", error=str(e))
            return []

# Singleton instance
tag_classifier = TagClassifier()
