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


# --- Phase 9 (T-6) admin dashboard addition ---
#
# No pagination convention existed anywhere in this codebase before this
# task (every pre-existing list endpoint — GET /bookings/mine — returns
# an unpaginated list, since one customer's own bookings is always a
# small set). The admin dashboard's list-ALL-customers/calls/bookings
# endpoints are a genuinely new shape (unbounded row count, staff
# scrolling through pages), so this is a new, explicit convention, not
# an existing one being followed.
class PageMeta(BaseModel):
    limit: int
    offset: int
    total: int
    has_more: bool


def make_page_meta(*, limit: int, offset: int, total: int) -> PageMeta:
    return PageMeta(limit=limit, offset=offset, total=total, has_more=(offset + limit) < total)
