"""
Payment routes (Phase 6 Milestone 1).

THIS FILE, LIKE THE REST OF app/api/routes/*.py, IS UNEXECUTED IN THIS
SANDBOX (no FastAPI install — see repo-wide sandbox note). Written and
reviewed against the exact method signatures of every service/repository/
security function it calls, following the same request/authorization
pattern already executed and proven by app/api/routes/bookings.py.

Two web routes (POST /sessions, GET /status/{pnr}) plus the Stripe
webhook receiver. The Vapi voice equivalents of the first two live
entirely in app/api/routes/vapi.py's dispatch table — both channels call
the SAME PaymentService methods (see that module's docstring), just
through different authorization gates:
  - Web (this file): require_payment_access — authenticated owner or
    FINANCE/ADMIN staff, NEVER a verification token (see
    app/api/deps_auth.py::require_payment_access's docstring).
  - Voice (vapi.py): the already-registered REQUIRES_VERIFIED_BOOKING
    matrix entries for create_payment_session/get_payment_status —
    unchanged from Phase 5, since sensitivity/permission were already
    correct before any payment backend existed. See docs/PAYMENTS.md
    "Authorization" for the full reasoning on why these are two
    deliberately different gates, not a gap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_idempotency_store, get_payment_provider
from app.api.deps_auth import get_current_actor, require_payment_access
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.security.actor import CurrentActor
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.models.payment import Payment
from app.repositories.booking_repository import BookingRepository
from app.schemas.common import ok
from app.schemas.payment import PaymentSessionCreateRequest, PaymentSessionOut, PaymentStatusOut
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

logger = get_logger(__name__)


def _payment_out(payment: Payment) -> PaymentSessionOut:
    return PaymentSessionOut(
        payment_id=str(payment.id),
        pnr=payment.booking.pnr,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        # Structured data only — never a claim the customer has this
        # link (see docs/PAYMENTS.md "Known limitation: out-of-band
        # delivery"). The web caller's own browser can act on this URL
        # directly; nothing here sends it anywhere on their behalf.
        checkout_url=payment.checkout_url,
        expires_at=payment.expires_at,
    )


def _actor_label(actor: CurrentActor) -> str:
    # This route is only ever reachable by a HUMAN_USER or staff actor —
    # require_payment_access() denies everything else unconditionally
    # (see its docstring) — so unlike bookings.py's _actor_label, there
    # is no call_id/anonymous fallback branch to consider here.
    return f"user:{actor.user_id}" if actor.user_id else "web_client"


@router.post("/sessions")
def create_payment_session(
    body: PaymentSessionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = BookingRepository(db).get_by_pnr(body.pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    effective_actor = require_payment_access(
        actor, booking=booking, required_permission=Permission.PAYMENTS_CREATE.value
    )

    service = PaymentService(db, get_payment_provider(), get_idempotency_store())
    payment = service.create_payment_session(
        body, actor=_actor_label(effective_actor), request_id=request.state.request_id,
    )
    return ok(_payment_out(payment), request.state.request_id)


@router.get("/status/{pnr}")
def get_payment_status(
    pnr: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    booking = BookingRepository(db).get_by_pnr(pnr)
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "No booking found for that confirmation number.")

    require_payment_access(actor, booking=booking, required_permission=Permission.PAYMENTS_READ.value)

    service = PaymentService(db, get_payment_provider(), get_idempotency_store())
    booking, payment = service.get_payment_status(pnr)
    return ok(
        PaymentStatusOut(
            pnr=booking.pnr,
            booking_payment_status=booking.payment_status,
            latest_payment=_payment_out(payment) if payment else None,
        ),
        request.state.request_id,
    )


# --------------------------------------------------------------------- webhook


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """No authentication dependency here on purpose — Stripe is not a
    logged-in user or a Vapi call; the Stripe-Signature header IS the
    authentication (§9), verified inside PaymentService.handle_webhook_
    event() -> PaymentProvider.verify_and_parse_webhook(). A bad
    signature raises WebhookVerificationError, which propagates to the
    PaymentProviderError handler registered in app/core/exceptions.py
    and becomes an HTTP 400 — never a 200, unlike the Vapi webhook's
    "always 200" contract (that convention is Vapi-specific; Stripe
    expects a normal HTTP status and will retry on non-2xx).

    Deliberately NOT rate-limited in this milestone (unlike the Vapi
    webhook's vapi_webhook rate-limit profile) — a request without a
    valid signature is rejected regardless of volume, so the
    security-relevant property doesn't depend on throttling the way an
    unauthenticated-until-checked endpoint would. Recorded as a scoped-
    out decision, not an oversight — see docs/PAYMENTS.md "Known
    limitations."
    """
    raw_payload = await request.body()
    signature_header = request.headers.get("stripe-signature")
    service = PaymentService(db, get_payment_provider(), get_idempotency_store())
    outcome = service.handle_webhook_event(raw_payload, signature_header)
    logger.info("stripe_webhook_processed", outcome=outcome)
    return {"received": True, "outcome": outcome}
