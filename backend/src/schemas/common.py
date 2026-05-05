from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str | None = None
    details: dict | None = None
