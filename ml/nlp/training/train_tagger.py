"""
Train SetFit Model for NLP Tagging (Phase 3).
"""

import sys
from pathlib import Path
import structlog
import pandas as pd
from datasets import Dataset

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.nlp.tag_classifier import _SUPPORTED_TAGS

logger = structlog.get_logger(__name__)

# Config
DATA_PATH = _REPO_ROOT / "ml" / "data" / "nlp_training.csv"
MODEL_SAVE_PATH = _REPO_ROOT / "ml" / "nlp" / "models" / "setfit_tagger"
BASE_MODEL = "sentence-transformers/paraphrase-MiniLM-L3-v2"

def train_setfit():
    """Train a SetFit model on the generated NLP dataset."""
    logger.info("nlp_training_started", data_path=str(DATA_PATH))
    
    if not DATA_PATH.exists():
        logger.error("nlp_data_not_found", data_path=str(DATA_PATH))
        print(f"Data not found at {DATA_PATH}. Please run generate_nlp_data.py first.")
        return
        
    try:
        from setfit import SetFitModel, Trainer, TrainingArguments
    except ImportError:
        logger.error("setfit_not_installed")
        print("Please install setfit: pip install setfit")
        return

    # Load data
    df = pd.read_csv(DATA_PATH)
    
    # Map string labels to integers
    label_to_id = {label: i for i, label in enumerate(_SUPPORTED_TAGS)}
    df['label_id'] = df['label'].map(label_to_id)
    
    # Split train/eval (80/20)
    df_train = df.sample(frac=0.8, random_state=42)
    df_eval = df.drop(df_train.index)
    
    train_dataset = Dataset.from_pandas(df_train)
    eval_dataset = Dataset.from_pandas(df_eval)
    
    # Initialize model
    logger.info("loading_base_model", model_name=BASE_MODEL)
    model = SetFitModel.from_pretrained(
        BASE_MODEL,
        labels=_SUPPORTED_TAGS,
    )
    
    # Set up training arguments
    args = TrainingArguments(
        batch_size=16,
        num_epochs=1, # Keep it small for fast training during dev
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
    )
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        metric="accuracy",
        column_mapping={"text": "text", "label_id": "label"} 
    )
    
    # Train
    logger.info("training_model")
    trainer.train()
    
    # Evaluate
    logger.info("evaluating_model")
    metrics = trainer.evaluate()
    logger.info("evaluation_metrics", metrics=metrics)
    
    accuracy = metrics.get('accuracy', 0)
    print(f"Training complete. Accuracy: {accuracy:.4f}")
    
    # Save model
    if accuracy >= 0.8:
        logger.info("promoting_model", save_path=str(MODEL_SAVE_PATH))
        MODEL_SAVE_PATH.mkdir(parents=True, exist_ok=True)
        # Using save_pretrained explicitly to save locally
        model.save_pretrained(str(MODEL_SAVE_PATH))
        print(f"Model saved to {MODEL_SAVE_PATH}")
    else:
        logger.warning("model_not_promoted", accuracy=accuracy, threshold=0.8)
        print("Model accuracy below threshold (0.8), not saving.")

if __name__ == "__main__":
    train_setfit()
