"""ML Router — /api/v1/ml"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.auth import Role, require_role
from ...core.database import get_db
from ...core.security import CurrentUser
from ...models import Task
from ...schemas.common import SuccessResponse
from ...services.ml_service import PredictionResult, ml_service

router = APIRouter(prefix="/ml", tags=["ML"])
limiter = Limiter(key_func=get_remote_address)


# ── Schemas ───────────────────────────────────────────────────────────────────


class PredictResponse(BaseModel):
    task_id: str
    predicted_hours: float
    confidence: float
    model_version: str
    latency_ms: float
    fallback: bool
    shap_values: dict[str, float] | None = None
    shap_base_value: float | None = None


class MLHealthResponse(BaseModel):
    model_loaded: bool
    model_version: str
    status: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/health", response_model=SuccessResponse[MLHealthResponse])
async def ml_health():
    """
    Kiem tra ML model da load thanh cong chua.
    Khong can auth — dung cho monitoring.
    """
    payload = MLHealthResponse(
        model_loaded=ml_service.is_ready,
        model_version=ml_service.model_version,
        status="ready" if ml_service.is_ready else "fallback",
    )
    return SuccessResponse(data=payload, message="ML service status")


@router.post(
    "/predict/{task_id}",
    response_model=SuccessResponse[PredictResponse],
)
@limiter.limit("30/minute")
async def predict_task_time(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    """
    Du doan actual_time cua 1 task.

    - Lay task data tu DB (filter theo org_id de dam bao multi-tenancy)
    - Chay ONNX inference qua MLService singleton
    - Shadow mode: log prediction, luu vao ml_predictions table

    Returns: predicted_hours, confidence, model_version, latency_ms, shap_values
    """
    # Lay task tu DB — filter org_id (multi-tenancy + IDOR prevention)
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.org_id == current_user.org_id,
            Task.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task khong ton tai hoac ban khong co quyen truy cap",
        )

    # Build task_data dict cho MLService
    task_data = {
        "title": task.title,
        "description": task.description,
        "priority_score": task.priority_score,
        "deadline": task.deadline,
        "assignee_workload": task.assignee_workload,
        "revision_count": task.revision_count,
        "tags": task.tags,
        "estimated_time": task.estimated_time,
    }

    # Inference
    prediction: PredictionResult = await ml_service.predict(task_data)

    # Luu vao ml_predictions table (shadow mode)
    from ...models import MLPrediction

    ml_pred = MLPrediction(
        task_id=task_id,
        org_id=task.org_id,
        model_version=prediction.model_version,
        feature_version=prediction.model_version,
        predicted_hours=prediction.predicted_hours,
        confidence=prediction.confidence,
        fallback=prediction.fallback,
        latency_ms=prediction.latency_ms,
        shap_values=prediction.shap_values,
        shap_base_value=prediction.shap_base_value,
    )
    db.add(ml_pred)
    await db.commit()

    payload = PredictResponse(
        task_id=str(task_id),
        predicted_hours=prediction.predicted_hours,
        confidence=prediction.confidence,
        model_version=prediction.model_version,
        latency_ms=prediction.latency_ms,
        fallback=prediction.fallback,
        shap_values=prediction.shap_values,
        shap_base_value=prediction.shap_base_value,
    )

    return SuccessResponse(
        data=payload,
        message=f"Du doan: {prediction.predicted_hours:.1f}h"
        + (" (fallback)" if prediction.fallback else ""),
    )
