from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_airline_provider
from app.api.deps_auth import get_current_actor, require_passenger_access
from app.core.exceptions import NotFoundError
from app.core.security.actor import ActorType, CurrentActor
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.repositories.booking_repository import BookingRepository
from app.schemas.common import ok
from app.schemas.passenger import PassengerCreate, PassportDetails
from app.services.passenger_service import PassengerService

router = APIRouter(prefix="/api/v1/passengers", tags=["passengers"])


def _actor_label(actor: CurrentActor, call_id: Optional[str]) -> str:
    if actor.actor_type == ActorType.HUMAN_USER and actor.user_id:
        return f"user:{actor.user_id}"
    return f"vapi_call:{call_id}" if call_id else "web_client"


def _load_booking_or_404(db: Session, pnr: str):
    booking = BookingRepository(db).get_by_pnr(pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")
    return booking


@router.post("/{pnr}")
def add_passenger(
    pnr: str,
    body: PassengerCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = _load_booking_or_404(db, pnr)
    effective_actor = require_passenger_access(
        actor,
        booking=booking,
        required_permission=Permission.PASSENGERS_MANAGE.value,
        verification_purpose="manage_passengers",
        verification_token=body.verification_token,
        db=db,
    )
    call_id = request.headers.get("x-charter123-call-id")
    service = PassengerService(db, get_airline_provider())
    booking = service.add_passenger(
        pnr, body, actor=_actor_label(effective_actor, call_id), call_id=call_id
    )
    return ok({"pnr": booking.pnr, "passenger_count": len(booking.passengers)}, request.state.request_id)


@router.delete("/{pnr}/{booking_passenger_id}")
def remove_passenger(
    pnr: str,
    booking_passenger_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
    verification_token: Optional[str] = None,
):
    booking = _load_booking_or_404(db, pnr)
    effective_actor = require_passenger_access(
        actor,
        booking=booking,
        required_permission=Permission.PASSENGERS_MANAGE.value,
        verification_purpose="manage_passengers",
        verification_token=verification_token,
        db=db,
    )
    call_id = request.headers.get("x-charter123-call-id")
    service = PassengerService(db, get_airline_provider())
    booking = service.remove_passenger(
        pnr, booking_passenger_id, actor=_actor_label(effective_actor, call_id), call_id=call_id
    )
    return ok({"pnr": booking.pnr, "passenger_count": len(booking.passengers)}, request.state.request_id)


@router.post("/{pnr}/{booking_passenger_id}/passport")
def add_passport_details(
    pnr: str,
    booking_passenger_id: str,
    body: PassportDetails,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    # Passport numbers are the most sensitive field this endpoint set
    # touches (§23) — held to exactly the same authorization bar as
    # cancel/modify, never a lower one.
    booking = _load_booking_or_404(db, pnr)
    effective_actor = require_passenger_access(
        actor,
        booking=booking,
        required_permission=Permission.PASSENGERS_MANAGE.value,
        verification_purpose="manage_passengers",
        verification_token=body.verification_token,
        db=db,
    )
    call_id = request.headers.get("x-charter123-call-id")
    service = PassengerService(db, get_airline_provider())
    booking = service.add_passport_details(
        pnr, booking_passenger_id, body, actor=_actor_label(effective_actor, call_id), call_id=call_id
    )
    return ok({"pnr": booking.pnr, "status": "passport_recorded"}, request.state.request_id)
