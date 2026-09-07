from app.models.aircraft import Aircraft  # noqa: F401
from app.models.airport import Airport  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.base import Base  # noqa: F401
from app.models.booking import Booking, BookingPassenger  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.idempotency import IdempotencyKeyRecord  # noqa: F401

# --- Phase 4: auth / RBAC / verification -----------------------------
from app.models.rbac import Permission, Role, RolePermission, UserRole  # noqa: F401
from app.models.session import Session  # noqa: F401
from app.models.tokens import EmailVerificationToken, PasswordResetToken  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.verification import VerificationSession  # noqa: F401

# --- Phase 5: Vapi voice agent ----------------------------------------
from app.models.call import Call  # noqa: F401
from app.models.tool_execution import ToolExecution  # noqa: F401

# --- Phase 6 Milestone 1: payments (Stripe) ----------------------------
from app.models.payment import Payment  # noqa: F401

__all__ = [
    "Base",
    "Aircraft",
    "Airport",
    "AuditLog",
    "Booking",
    "BookingPassenger",
    "Customer",
    "IdempotencyKeyRecord",
    # Phase 4
    "User",
    "Session",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "VerificationSession",
    "PasswordResetToken",
    "EmailVerificationToken",
    # Phase 5
    "Call",
    "ToolExecution",
    # Phase 6 Milestone 1
    "Payment",
]
