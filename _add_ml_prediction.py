"""Script to append MLPrediction model to models/__init__.py"""
from pathlib import Path

models_file = Path("backend/src/models/__init__.py")
content = models_file.read_bytes()

ML_PREDICTION_CODE = b"""

# --- MLPrediction (Phase 2 - Shadow Mode) ------------------------------------


class MLPrediction(Base):
    \"\"\"
    Luu ket qua ML prediction theo Shadow Mode.

    Shadow Mode:
      - Model chay inference background sau khi task duoc tao
      - Ket qua KHONG hien thi cho user ngay (chua tin tuong)
      - Khi task DONE -> actual_time -> error = actual - predicted
      - Dung de danh gia chinh xac truoc khi promote model moi
    \"\"\"

    __tablename__ = "ml_predictions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    org_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_hours: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    shap_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shap_base_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["Task"] = relationship("Task", back_populates="ml_predictions")

    __table_args__ = (
        Index("ix_ml_predictions_task_id", "task_id"),
        Index("ix_ml_predictions_org_id", "org_id"),
        Index("ix_ml_predictions_model_version", "model_version"),
        Index("ix_ml_predictions_created_at", "created_at"),
    )

"""

OLD_ALL = b'"AuditLog",\r\n    "UserRole",'
NEW_ALL = b'"AuditLog",\r\n    "MLPrediction",\r\n    "UserRole",'

# Find insertion point (before __all__)
marker = b"__all__"
insert_pos = content.find(marker)
assert insert_pos != -1, "Could not find __all__ marker"

new_content = content[:insert_pos] + ML_PREDICTION_CODE + content[insert_pos:]
new_content = new_content.replace(OLD_ALL, NEW_ALL)

models_file.write_bytes(new_content)
print(f"Done. File size: {models_file.stat().st_size} bytes")
print(f"MLPrediction in file: {'MLPrediction' in models_file.read_text(encoding='utf-8', errors='replace')}")
