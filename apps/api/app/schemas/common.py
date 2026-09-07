from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class Envelope(BaseModel, Generic[T]):
    """Every API response follows this shape (§36):
    {"success": true, "data": {...}, "request_id": "..."}
    {"success": false, "error": {"code": "...", "message": "..."}, "request_id": "..."}
    """

    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    request_id: str


def ok(data: T, request_id: str) -> Envelope[T]:
    return Envelope[T](success=True, data=data, request_id=request_id)
