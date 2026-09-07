from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_airline_provider, get_idempotency_store
from app.api.deps_auth import get_current_actor, require_booking_access
from app.core.encryption import decrypt_sensitive, mask_for_speech
from app.core.exceptions import AuthError, NotFoundError
from app.core.logging import get_logger
from app.core.security.actor import ActorType, CurrentActor
from app.core.security.errors import AuthErrorCode
from app.core.security.ownership import authorize_booking_access
from app.core.security.rate_limiter import BackoffLockout, build_rate_limiter
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.models.booking import Booking, BookingPassenger
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import (
    BookingCancelRequest,
    BookingCreateRequest,
    BookingLookupRequest,
    BookingModifyRequest,
    BookingOut,
    BookingVerifyOut,
    BookingVerifyRequest,
    CancellationQuoteOut,
)
from app.schemas.common import ok
from app.schemas.passenger import PassengerOut
from app.services.booking_service import BookingService
from app.services.cancellation_service import CancellationService
from app.services.rate_limit_service import RedisRateLimitStore
from app.services.verification_service import VerificationSessionService

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


logger = get_logger(__name__)


def _masked_passport(p: BookingPassenger) -> str | None:
    """Decrypts only to derive a last-4 masked display (§10: never expose
    or log the full number). If decryption fails for any reason we still
    must not error the whole booking response — fall back to a generic
    'on file' indicator."""
    if not p.passport_number_encrypted:
        return None
    try:
        return mask_for_speech(decrypt_sensitive(p.passport_number_encrypted))
    except Exception:
        logger.warning("passport_decrypt_failed_for_display", passenger_id=str(p.id))
        return "passport on file"


def _passenger_out(p: BookingPassenger) -> PassengerOut:
    return PassengerOut(
        id=str(p.id), first_name=p.first_name, middle_name=p.middle_name, last_name=p.last_name,
        passenger_type=p.passenger_type, meal_preference=p.meal_preference, seat_preference=p.seat_preference,
        special_assistance=p.special_assistance, frequent_flyer_number=p.frequent_flyer_number,
        passport_on_file=p.passport_number_encrypted is not None,
        passport_number_masked=_masked_passport(p),
    )


def _booking_out(b: Booking) -> BookingOut:
    return BookingOut(
        pnr=b.pnr, status=b.status, payment_status=b.payment_status,
        origin=b.origin, destination=b.destination, flight_number=b.flight_number,
        aircraft_type=b.aircraft_type, departure_time=b.departure_time, arrival_time=b.arrival_time,
        currency=b.currency, total_price=b.total_price,
        passengers=[_passenger_out(p) for p in b.passengers],
        cancellation_deadline=b.cancellation_deadline,
    )


def _actor_label(actor: CurrentActor, call_id: str | None) -> str:
    """Audit-log attribution string. Prior to Phase 4 this was derived
    purely from a client-supplied call-id header; now it prefers the
    session-derived identity when one exists, falling back to the same
    call-id/web_client label as before for anonymous/voice requests —
    see docs/SECURITY.md 'Audit logging'."""
    if actor.actor_type == ActorType.HUMAN_USER and actor.user_id:
        return f"user:{actor.user_id}"
    if call_id:
        return f"vapi_call:{call_id}"
    return "web_client"


@router.post("")
def create_booking(body: BookingCreateRequest, request: Request, db: Session = Depends(get_db)):
    service = BookingService(db, get_airline_provider(), get_idempotency_store())
    call_id = request.headers.get("x-charter123-call-id")
    actor = f"vapi_call:{call_id}" if call_id else "web_client"
    booking = service.create_booking(body, actor=actor, call_id=call_id, request_id=request.state.request_id)
    return ok(_booking_out(booking), request.state.request_id)


@router.post("/lookup")
def lookup_booking(
    body: BookingLookupRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = BookingRepository(db).get_by_pnr(body.pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    # AUTHENTICATED CUSTOMER ACCESS (§11): a signed-in owner (or staff)
    # skips the email/phone/last-name dance entirely — ownership is
    # already proven by the session. Falls through to the existing
    # anonymous verification path below for anyone this doesn't cover,
    # so nothing about the previously-tested anonymous flow changes.
    if actor.actor_type == ActorType.HUMAN_USER:
        decision = authorize_booking_access(
            actor,
            booking_customer_id=(str(booking.customer_id) if booking.customer_id else None),
            booking_id=str(booking.id),
            required_permission=Permission.BOOKINGS_READ.value,
            verification_purpose="view_booking",
        )
        if decision.allowed:
            return ok(_booking_out(booking), request.state.request_id)

    # PUBLIC/VOICE LOOKUP (§11): unchanged one-shot PNR + email-or-phone
    # + last-name check (BookingVerificationService.verify(), Phase 1-3),
    # now additionally rate-limited (§17 explicitly lists booking_lookup)
    # so it can't be used as an unlimited PNR/identity-guessing oracle.
    limiter = build_rate_limiter("booking_lookup", RedisRateLimitStore())
    if not limiter.check(f"pnr:{body.pnr}").allowed:
        raise AuthError(AuthErrorCode.RATE_LIMITED, "Too many attempts. Please wait a moment and try again.")

    service = BookingService(db, get_airline_provider(), get_idempotency_store())
    verified_booking = service.get_verified_booking(
        body.pnr, email_or_phone=body.verification_email_or_phone, last_name=body.verification_last_name,
    )
    return ok(_booking_out(verified_booking), request.state.request_id)


@router.get("/mine")
def list_my_bookings(
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    """AUTHENTICATED CUSTOMER ACCESS (§11) — new in Phase 4. Requires a
    signed-in customer; deliberately does NOT accept a customer_id query
    param at all (§10) — the only customer whose bookings this can ever
    return is actor.customer_id, straight from the session."""
    if actor.actor_type != ActorType.HUMAN_USER or not actor.customer_id:
        raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "Please sign in to continue.")
    bookings = BookingRepository(db).list_for_customer(actor.customer_id)
    return ok([_booking_out(b) for b in bookings], request.state.request_id)


@router.get("/{pnr}/cancellation-policy")
def get_cancellation_policy(pnr: str, request: Request, db: Session = Depends(get_db)):
    service = CancellationService(db, get_airline_provider(), get_idempotency_store())
    booking, policy = service.get_policy(pnr)
    out = CancellationQuoteOut(
        pnr=booking.pnr, refundable_amount=policy.refundable_amount,
        cancellation_fee=policy.cancellation_fee, currency=policy.currency,
        already_cancelled=policy.already_cancelled,
    )
    return ok(out, request.state.request_id)


@router.post("/{pnr}/verify")
def verify_booking(
    pnr: str,
    body: BookingVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """§12: the controlled verification flow that
    cancel/modify/passenger-mutation routes require from an anonymous or
    voice caller in place of the old, insufficient
    `customer_confirmed: bool`. Rate-limited tightly (§17's
    "booking_verification" profile — 5 attempts / 10 minutes / booking)
    since this is the guessing-resistance boundary for someone else's
    PNR + contact details."""
    if body.pnr != pnr:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")
    booking = BookingRepository(db).get_by_pnr(pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    lockout = BackoffLockout(RedisRateLimitStore())
    if not lockout.is_locked(f"verify:{booking.id}").allowed:
        raise AuthError(AuthErrorCode.RATE_LIMITED, "Too many verification attempts. Please try again shortly.")

    verification = VerificationSessionService(db, rate_limiter=lockout)
    call_id = request.headers.get("x-charter123-call-id")
    raw_token = body.verification_token or verification.start(
        booking_id=str(booking.id), purpose=body.purpose, call_id=call_id
    )
    record = verification.submit(
        raw_token=raw_token, booking=booking, email_or_phone=body.email_or_phone, last_name=body.last_name
    )
    return ok(
        BookingVerifyOut(status=record.status, verification_token=raw_token, attempts=record.attempts),
        request.state.request_id,
    )


@router.post("/cancel")
def cancel_booking(
    body: BookingCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = BookingRepository(db).get_by_pnr(body.pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    effective_actor = require_booking_access(
        actor,
        booking=booking,
        required_permission=Permission.BOOKINGS_CANCEL.value,
        verification_purpose="cancel_booking",
        verification_token=body.verification_token,
        db=db,
    )

    call_id = request.headers.get("x-charter123-call-id")
    service = CancellationService(db, get_airline_provider(), get_idempotency_store())
    booking, already_cancelled = service.cancel(
        body, actor=_actor_label(effective_actor, call_id), call_id=call_id, request_id=request.state.request_id
    )
    result = _booking_out(booking).model_dump()
    result["already_cancelled"] = already_cancelled
    return ok(result, request.state.request_id)


@router.post("/modify")
def modify_booking(
    body: BookingModifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = BookingRepository(db).get_by_pnr(body.pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    effective_actor = require_booking_access(
        actor,
        booking=booking,
        required_permission=Permission.BOOKINGS_MODIFY.value,
        verification_purpose="modify_booking",
        verification_token=body.verification_token,
        db=db,
    )

    call_id = request.headers.get("x-charter123-call-id")
    service = BookingService(db, get_airline_provider(), get_idempotency_store())
    booking = service.modify_booking(
        body, actor=_actor_label(effective_actor, call_id), call_id=call_id, request_id=request.state.request_id
    )
    return ok(_booking_out(booking), request.state.request_id)
