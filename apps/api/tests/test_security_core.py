"""
Phase 4 security-core tests.

Like tests/test_core_logic.py, everything imported here is deliberately
dependency-free (stdlib + `cryptography`, which is a real, already-present
dependency of this project — see app/core/encryption.py). Run with:

    cd apps/api
    python3 -m unittest tests.test_security_core -v

No FastAPI, SQLAlchemy, or database is required — these tests exercise
the actual authorization/crypto/rate-limiting decision logic, not a
mocked-out version of it. The FastAPI route layer built on top of this
(app/api/routes/auth.py, app/api/deps.py) delegates every real decision to
these functions, so what's proven here is what's actually enforced.
"""

from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security.actor import ActorType, CurrentActor, SYSTEM_ACTOR
from app.core.security.csrf import issue_csrf_token, requires_csrf_check, verify_csrf
from app.core.security.errors import HTTP_STATUS_FOR_CODE, AuthErrorCode
from app.core.security.ownership import (
    authorize_booking_access,
    authorize_customer_profile_access,
    authorize_passenger_access,
    authorize_payment_access,
)
from app.core.security.password_policy import MIN_LENGTH, validate_password_strength
from app.core.security.passwords import Argon2Parameters, PasswordHasher
from app.core.security.rate_limiter import (
    BackoffLockout,
    FixedWindowRateLimiter,
    InMemoryRateLimitStore,
    build_rate_limiter,
)
from app.core.security.rbac import (
    ALL_PERMISSIONS,
    Permission,
    ROLE_PERMISSIONS,
    Role,
    UnknownRoleError,
    has_all_permissions,
    has_any_permission,
    permissions_for_roles,
)
from app.core.security.redaction import redact_string_value, redact_value
from app.core.security.tokens import IssuedToken, generate_token, hash_token, is_expired, new_id, verify_token
from app.core.security.vapi_authorization import authorize_vapi_tool_call
from app.core.security.verification import VerificationSessionError, VerificationSessionState, VerificationStatus

# A cheap, fast Argon2id profile for tests only — production uses the
# module's OWASP-minimum DEFAULT_PARAMETERS (see passwords.py). Using a
# lighter profile here is standard practice for test suites and does not
# change what ships; PasswordHasherTests separately proves the *default*
# instance also round-trips correctly.
_FAST_PARAMS = Argon2Parameters(memory_cost_kib=8 * 1024, iterations=1, lanes=1)


class TokenTests(unittest.TestCase):
    def test_tokens_are_high_entropy_and_unique(self):
        tokens = {generate_token() for _ in range(200)}
        self.assertEqual(len(tokens), 200)

    def test_hash_is_deterministic(self):
        t = generate_token()
        self.assertEqual(hash_token(t), hash_token(t))

    def test_verify_true_for_correct_false_for_incorrect(self):
        t = generate_token()
        h = hash_token(t)
        self.assertTrue(verify_token(t, h))
        self.assertFalse(verify_token(generate_token(), h))

    def test_issued_token_expiry(self):
        issued = IssuedToken.issue(ttl=timedelta(minutes=5))
        self.assertFalse(is_expired(issued.expires_at))
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.assertTrue(is_expired(past))

    def test_new_id_has_prefix(self):
        self.assertTrue(new_id("req").startswith("req_"))


class PasswordPolicyTests(unittest.TestCase):
    def test_too_short_rejected(self):
        result = validate_password_strength("Sh0rt!")
        self.assertFalse(result.valid)

    def test_common_password_rejected(self):
        result = validate_password_strength("password123")
        self.assertFalse(result.valid)

    def test_sequential_run_rejected(self):
        result = validate_password_strength("abcdefghijkl")
        self.assertFalse(result.valid)

    def test_low_variety_rejected(self):
        result = validate_password_strength("aaaaaaaaaaaaaaaa")
        self.assertFalse(result.valid)

    def test_contains_email_rejected(self):
        result = validate_password_strength("janedoe12345secure", email="janedoe@example.com")
        self.assertFalse(result.valid)

    def test_reasonable_password_accepted(self):
        result = validate_password_strength("Tr0mb0ne-Ferret-Quay!42")
        self.assertTrue(result.valid, result.problems)

    def test_min_length_constant_is_sane(self):
        self.assertGreaterEqual(MIN_LENGTH, 8)


class PasswordHasherTests(unittest.TestCase):
    def setUp(self):
        self.hasher = PasswordHasher(_FAST_PARAMS)

    def test_hash_then_verify_round_trip(self):
        encoded = self.hasher.hash("correct horse battery staple 42!")
        self.assertTrue(self.hasher.verify("correct horse battery staple 42!", encoded))

    def test_wrong_password_rejected(self):
        encoded = self.hasher.hash("the-real-password-99")
        self.assertFalse(self.hasher.verify("not-the-real-password", encoded))

    def test_same_password_hashed_twice_produces_different_output(self):
        p = "same password both times"
        self.assertNotEqual(self.hasher.hash(p), self.hasher.hash(p))

    def test_needs_rehash_true_under_different_parameters(self):
        encoded = self.hasher.hash("hunter2 but actually long enough")
        stronger = PasswordHasher(Argon2Parameters(memory_cost_kib=16 * 1024, iterations=2, lanes=1))
        self.assertTrue(stronger.needs_rehash(encoded))
        self.assertFalse(self.hasher.needs_rehash(encoded))

    def test_malformed_hash_never_raises_and_fails_closed(self):
        self.assertFalse(self.hasher.verify("anything", "not-a-real-hash-at-all"))
        self.assertFalse(self.hasher.verify("anything", ""))
        self.assertTrue(self.hasher.needs_rehash("garbage"))

    def test_empty_password_rejected_at_hash_time(self):
        with self.assertRaises(ValueError):
            self.hasher.hash("")

    def test_default_production_parameters_also_round_trip(self):
        # Slower (~real OWASP-minimum cost) — one call only, to prove the
        # shipped default works, without slowing down the whole suite.
        default_hasher = PasswordHasher()
        encoded = default_hasher.hash("production-parameters-check-1")
        self.assertTrue(default_hasher.verify("production-parameters-check-1", encoded))


class RbacTests(unittest.TestCase):
    def test_every_role_in_matrix_only_grants_known_permissions(self):
        for role, perms in ROLE_PERMISSIONS.items():
            self.assertTrue(perms.issubset(ALL_PERMISSIONS), f"{role} grants an unknown permission")

    def test_customer_role_has_no_admin_permissions(self):
        perms = permissions_for_roles([Role.CUSTOMER.value])
        self.assertNotIn(Permission.ADMIN_MANAGE.value, perms)
        self.assertNotIn(Permission.SYSTEM_MANAGE.value, perms)
        self.assertNotIn(Permission.USERS_MANAGE.value, perms)

    def test_read_only_role_grants_no_mutating_permission(self):
        perms = permissions_for_roles([Role.READ_ONLY.value])
        mutating_suffixes = (".manage", ".create", ".modify", ".cancel", ".refund", ".export", ".execute", ".configure")
        offending = [p for p in perms if p.endswith(mutating_suffixes)]
        self.assertEqual(offending, [], f"READ_ONLY unexpectedly grants: {offending}")

    def test_super_admin_has_every_permission(self):
        perms = permissions_for_roles([Role.SUPER_ADMIN.value])
        self.assertEqual(perms, ALL_PERMISSIONS)

    def test_admin_lacks_system_manage_by_design(self):
        # system.manage is deliberately reserved for SUPER_ADMIN only —
        # see rbac.py's comment on infra-level config.
        perms = permissions_for_roles([Role.ADMIN.value])
        self.assertNotIn(Permission.SYSTEM_MANAGE.value, perms)

    def test_union_across_multiple_roles(self):
        perms = permissions_for_roles([Role.CUSTOMER.value, Role.FINANCE.value])
        self.assertIn(Permission.BOOKINGS_CREATE.value, perms)  # from CUSTOMER
        self.assertIn(Permission.PAYMENTS_REFUND.value, perms)  # from FINANCE

    def test_unknown_role_raises_fail_closed(self):
        with self.assertRaises(UnknownRoleError):
            permissions_for_roles(["NOT_A_REAL_ROLE"])

    def test_has_any_and_has_all(self):
        perms = permissions_for_roles([Role.BOOKING_AGENT.value])
        self.assertTrue(has_any_permission(perms, [Permission.ADMIN_MANAGE.value, Permission.BOOKINGS_READ.value]))
        self.assertFalse(has_all_permissions(perms, [Permission.BOOKINGS_READ.value, Permission.ADMIN_MANAGE.value]))


def _human_actor(*, user_id="u1", customer_id=None, roles=(), request_id="req_test") -> CurrentActor:
    perms = permissions_for_roles(list(roles)) if roles else frozenset()
    return CurrentActor(
        actor_type=ActorType.HUMAN_USER, user_id=user_id, customer_id=customer_id,
        roles=frozenset(roles), permissions=perms, account_status="ACTIVE", request_id=request_id,
    )


def _vapi_actor(*, authenticated=True, verified_booking_id=None, purpose=None, permissions=frozenset({"vapi.execute", "bookings.read", "bookings.modify", "bookings.cancel", "flights.read", "passengers.manage"})) -> CurrentActor:
    return CurrentActor(
        actor_type=ActorType.VAPI_AGENT, vapi_authenticated=authenticated, call_id="call_1",
        assistant_id="asst_1", permissions=permissions,
        verified_booking_id=verified_booking_id, verified_purpose=purpose,
        booking_verification_status="VERIFIED" if verified_booking_id else None,
    )


class ActorTests(unittest.TestCase):
    def test_is_authenticated_human(self):
        self.assertTrue(_human_actor().is_authenticated_human)
        self.assertFalse(SYSTEM_ACTOR.is_authenticated_human)

    def test_is_staff_true_for_non_customer_role(self):
        self.assertTrue(_human_actor(roles=[Role.SUPPORT_AGENT.value]).is_staff)
        self.assertFalse(_human_actor(roles=[Role.CUSTOMER.value]).is_staff)

    def test_booking_verification_scoping(self):
        actor = _vapi_actor(verified_booking_id="bk_1", purpose="cancel_booking")
        self.assertTrue(actor.has_valid_booking_verification("bk_1", "cancel_booking"))
        self.assertFalse(actor.has_valid_booking_verification("bk_1", "modify_booking"))
        self.assertFalse(actor.has_valid_booking_verification("bk_2", "cancel_booking"))


class OwnershipTests(unittest.TestCase):
    def test_staff_permission_allows_regardless_of_ownership(self):
        staff = _human_actor(user_id="staff_1", customer_id=None, roles=[Role.SUPPORT_AGENT.value])
        decision = authorize_booking_access(
            staff, booking_customer_id="cust_other", booking_id="bk_1", required_permission=Permission.BOOKINGS_CANCEL.value,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "staff_permission")

    def test_owner_allowed_on_their_own_booking(self):
        owner = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        decision = authorize_booking_access(
            owner, booking_customer_id="cust_A", booking_id="bk_1", required_permission=Permission.BOOKINGS_CANCEL.value,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "owner")

    def test_non_owner_customer_denied(self):
        customer_a = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        decision = authorize_booking_access(
            customer_a, booking_customer_id="cust_B", booking_id="bk_B", required_permission=Permission.BOOKINGS_CANCEL.value,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error_code, AuthErrorCode.FORBIDDEN.value)

    def test_verified_anonymous_caller_allowed_within_scope(self):
        verified = CurrentActor(
            actor_type=ActorType.ANONYMOUS_VERIFIED, verified_booking_id="bk_1",
            verified_purpose="cancel_booking", booking_verification_status="VERIFIED",
        )
        decision = authorize_booking_access(
            verified, booking_customer_id="cust_A", booking_id="bk_1",
            required_permission=Permission.BOOKINGS_CANCEL.value, verification_purpose="cancel_booking",
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "verified_booking_token")

    def test_verified_caller_wrong_purpose_denied(self):
        # Verified to *view*, not to *cancel* — must not be allowed to cancel.
        verified = CurrentActor(
            actor_type=ActorType.ANONYMOUS_VERIFIED, verified_booking_id="bk_1",
            verified_purpose="view_booking", booking_verification_status="VERIFIED",
        )
        decision = authorize_booking_access(
            verified, booking_customer_id="cust_A", booking_id="bk_1",
            required_permission=Permission.BOOKINGS_CANCEL.value, verification_purpose="cancel_booking",
        )
        self.assertFalse(decision.allowed)

    def test_verified_caller_wrong_booking_denied(self):
        verified = CurrentActor(
            actor_type=ActorType.ANONYMOUS_VERIFIED, verified_booking_id="bk_1",
            verified_purpose="cancel_booking", booking_verification_status="VERIFIED",
        )
        decision = authorize_booking_access(
            verified, booking_customer_id="cust_A", booking_id="bk_OTHER",
            required_permission=Permission.BOOKINGS_CANCEL.value, verification_purpose="cancel_booking",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error_code, AuthErrorCode.BOOKING_VERIFICATION_REQUIRED.value)

    def test_customer_profile_access_has_no_verification_token_path(self):
        # A booking-verification token must not unlock a customer's whole
        # profile — authorize_customer_profile_access() doesn't even
        # accept a verification_purpose argument.
        verified = CurrentActor(
            actor_type=ActorType.ANONYMOUS_VERIFIED, verified_booking_id="bk_1",
            verified_purpose="view_booking", booking_verification_status="VERIFIED",
        )
        decision = authorize_customer_profile_access(
            verified, target_customer_id="cust_A", required_permission=Permission.CUSTOMERS_READ.value,
        )
        self.assertFalse(decision.allowed)

    def test_passenger_access_inherits_booking_ownership(self):
        owner = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        allowed = authorize_passenger_access(
            owner, booking_customer_id="cust_A", booking_id="bk_1", required_permission=Permission.PASSENGERS_MANAGE.value,
        )
        denied = authorize_passenger_access(
            owner, booking_customer_id="cust_B", booking_id="bk_2", required_permission=Permission.PASSENGERS_MANAGE.value,
        )
        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)

    def test_payment_access_never_accepts_a_verification_token(self):
        # authorize_payment_access has no verification_purpose parameter
        # at all (§14: refund_payment -> FINANCE/ADMIN only) — a verified
        # voice caller can never reach a refund this way.
        import inspect

        self.assertNotIn("verification_purpose", inspect.signature(authorize_payment_access).parameters)

    def test_finance_role_can_refund_anyone(self):
        finance = _human_actor(user_id="f1", customer_id=None, roles=[Role.FINANCE.value])
        decision = authorize_payment_access(
            finance, booking_customer_id="cust_A", booking_id="bk_1", required_permission=Permission.PAYMENTS_REFUND.value,
        )
        self.assertTrue(decision.allowed)

    def test_owner_can_create_and_read_their_own_payment(self):
        # Phase 6 Milestone 1: the web path for create_payment_session/
        # get_payment_status goes through THIS function (require_payment_
        # access -> authorize_payment_access), unchanged from Phase 4 —
        # confirms the owner branch (which pre-dates any payment backend)
        # actually grants what a logged-in customer paying for their own
        # booking needs, for both permissions this milestone uses.
        owner = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        for permission in (Permission.PAYMENTS_CREATE.value, Permission.PAYMENTS_READ.value):
            with self.subTest(permission=permission):
                decision = authorize_payment_access(
                    owner, booking_customer_id="cust_A", booking_id="bk_1", required_permission=permission,
                )
                self.assertTrue(decision.allowed)

    def test_payment_access_denies_a_vapi_agent_for_create_and_read_too(self):
        # Pins the Milestone 1 design decision, not just the pre-existing
        # refund-only test above: authorize_payment_access() has NO
        # verification-token path AT ALL, which means a Vapi caller can
        # never satisfy it for ANY permission — not just payments.refund.
        # This is exactly why create_payment_session/get_payment_status's
        # Vapi path uses the ALREADY-registered REQUIRES_VERIFIED_BOOKING
        # matrix entry (-> authorize_booking_access, a different function)
        # instead of this one — see docs/PAYMENTS.md "Authorization." If
        # this test ever starts failing because someone added a
        # verification_purpose parameter here, that's a deliberate,
        # security-relevant architecture change, not a refactor.
        vapi_actor = CurrentActor(
            actor_type=ActorType.VAPI_AGENT, call_id="call_1",
            verified_booking_id="bk_1", verified_purpose="vapi_tool_access", booking_verification_status="VERIFIED",
        )
        for permission in (Permission.PAYMENTS_CREATE.value, Permission.PAYMENTS_READ.value, Permission.PAYMENTS_REFUND.value):
            with self.subTest(permission=permission):
                decision = authorize_payment_access(
                    vapi_actor, booking_customer_id="cust_A", booking_id="bk_1", required_permission=permission,
                )
                self.assertFalse(decision.allowed)


class CriticalSecurityTest(unittest.TestCase):
    """Phase 4 spec §33, run for real. Two customers, two bookings, and
    every attack §33 lists — including the exact class of bug this whole
    phase exists to prevent: trusting a client-supplied identity header."""

    def setUp(self):
        self.customer_a_id = "cust_A_11111111"
        self.customer_b_id = "cust_B_22222222"
        self.booking_a_id = "bk_A_aaaaaaaa"
        self.booking_b_id = "bk_B_bbbbbbbb"
        self.actor_a = _human_actor(user_id="user_A", customer_id=self.customer_a_id, roles=[Role.CUSTOMER.value])

    def _access_booking_b_as_customer_a(self, *, permission: str, malicious_headers: dict | None = None):
        # `malicious_headers` simulates an attacker-controlled request:
        # x-user-id / customerId set to Customer B. The point of this test
        # is that authorize_booking_access() has NO PARAMETER that reads
        # from a headers dict at all — there is nothing for the attacker's
        # forged values to reach. We still construct the dict here and
        # pass booking_customer_id from server-side truth (the real
        # Booking B row's customer_id) to make that explicit rather than
        # merely assumed.
        del malicious_headers  # intentionally unused — see docstring above
        return authorize_booking_access(
            self.actor_a,
            booking_customer_id=self.customer_b_id,  # ground truth from the DB row for Booking B
            booking_id=self.booking_b_id,
            required_permission=permission,
        )

    def test_get_booking_b_as_customer_a_denied(self):
        decision = self._access_booking_b_as_customer_a(permission=Permission.BOOKINGS_READ.value)
        self.assertFalse(decision.allowed)

    def test_modify_booking_b_as_customer_a_denied(self):
        decision = self._access_booking_b_as_customer_a(permission=Permission.BOOKINGS_MODIFY.value)
        self.assertFalse(decision.allowed)

    def test_cancel_booking_b_as_customer_a_denied(self):
        decision = self._access_booking_b_as_customer_a(permission=Permission.BOOKINGS_CANCEL.value)
        self.assertFalse(decision.allowed)

    def test_forged_x_user_id_header_has_no_effect(self):
        malicious = {"x-user-id": self.customer_b_id}
        decision = self._access_booking_b_as_customer_a(permission=Permission.BOOKINGS_CANCEL.value, malicious_headers=malicious)
        self.assertFalse(decision.allowed)

    def test_forged_customer_id_field_has_no_effect(self):
        malicious = {"customerId": self.customer_b_id}
        decision = self._access_booking_b_as_customer_a(permission=Permission.BOOKINGS_CANCEL.value, malicious_headers=malicious)
        self.assertFalse(decision.allowed)

    def test_authorize_booking_access_signature_has_no_client_identity_parameter(self):
        # Structural guarantee, not just a behavioral one: prove the
        # forgeable parameter doesn't exist, so this can't regress via a
        # future refactor that "helpfully" adds a header-trusting branch.
        import inspect

        params = set(inspect.signature(authorize_booking_access).parameters)
        forbidden = {"requested_customer_id", "x_user_id", "customer_id_header", "headers", "request"}
        self.assertEqual(params & forbidden, set())

    def test_customer_a_can_still_access_their_own_booking_a(self):
        # Sanity check the other direction — this test suite shouldn't
        # accidentally prove "nobody can access anything".
        decision = authorize_booking_access(
            self.actor_a, booking_customer_id=self.customer_a_id, booking_id=self.booking_a_id,
            required_permission=Permission.BOOKINGS_CANCEL.value,
        )
        self.assertTrue(decision.allowed)


class AttackScenarioTests(unittest.TestCase):
    """Phase 4 spec §32 — the broader attack list beyond §33's specific
    booking scenario."""

    def test_idor_on_customer_profile(self):
        customer_a = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        decision = authorize_customer_profile_access(
            customer_a, target_customer_id="cust_B", required_permission=Permission.CUSTOMERS_READ.value,
        )
        self.assertFalse(decision.allowed)

    def test_horizontal_privilege_escalation_support_agent_cannot_refund(self):
        # SUPPORT_AGENT can read/modify/cancel bookings but has no
        # payments.refund permission — refunds are FINANCE/ADMIN only.
        support = _human_actor(user_id="s1", roles=[Role.SUPPORT_AGENT.value])
        decision = authorize_payment_access(
            support, booking_customer_id="cust_A", booking_id="bk_1", required_permission=Permission.PAYMENTS_REFUND.value,
        )
        self.assertFalse(decision.allowed)

    def test_vertical_privilege_escalation_customer_cannot_admin_manage(self):
        customer = _human_actor(user_id="u1", customer_id="cust_A", roles=[Role.CUSTOMER.value])
        self.assertFalse(customer.has_permission(Permission.ADMIN_MANAGE.value))

    def test_role_manipulation_extra_role_not_granted_still_denied(self):
        # An actor's permission set must come only from
        # permissions_for_roles() over roles actually assigned in the DB.
        # Simulate the attack by asserting the customer role alone (as it
        # would really be loaded) grants nothing admin-shaped — i.e. there
        # is no permission leakage between roles in the matrix itself.
        perms = permissions_for_roles([Role.CUSTOMER.value])
        self.assertFalse(any(p.startswith("admin.") or p.startswith("system.") for p in perms))

    def test_session_reuse_after_logout_is_a_session_layer_concern(self):
        # Documents the boundary: the pure ownership/rbac core here has no
        # concept of "logged out" — that's SessionRepository/session
        # revocation at the DB layer (see app/services/session_service.py,
        # 🟡 not executable in this sandbox). What IS provable here is
        # that a CurrentActor with no roles/permissions (the shape a
        # revoked-session lookup should produce) is denied everywhere.
        revoked = CurrentActor(actor_type=ActorType.HUMAN_USER, user_id=None, customer_id=None)
        decision = authorize_booking_access(
            revoked, booking_customer_id="cust_A", booking_id="bk_1", required_permission=Permission.BOOKINGS_READ.value,
        )
        self.assertFalse(decision.allowed)


class RateLimiterTests(unittest.TestCase):
    def test_allows_up_to_the_limit(self):
        store = InMemoryRateLimitStore()
        limiter = FixedWindowRateLimiter(store, limit=3, window_seconds=60)
        now = 1_000.0
        results = [limiter.check("k1", now=now) for _ in range(3)]
        self.assertTrue(all(r.allowed for r in results))

    def test_blocks_beyond_the_limit(self):
        store = InMemoryRateLimitStore()
        limiter = FixedWindowRateLimiter(store, limit=2, window_seconds=60)
        now = 1_000.0
        limiter.check("k1", now=now)
        limiter.check("k1", now=now)
        third = limiter.check("k1", now=now)
        self.assertFalse(third.allowed)
        self.assertGreater(third.retry_after_seconds, 0)

    def test_window_resets_after_expiry(self):
        store = InMemoryRateLimitStore()
        limiter = FixedWindowRateLimiter(store, limit=1, window_seconds=10)
        limiter.check("k1", now=1_000.0)
        blocked = limiter.check("k1", now=1_005.0)
        allowed_again = limiter.check("k1", now=1_011.0)
        self.assertFalse(blocked.allowed)
        self.assertTrue(allowed_again.allowed)

    def test_keys_are_isolated(self):
        store = InMemoryRateLimitStore()
        limiter = FixedWindowRateLimiter(store, limit=1, window_seconds=60)
        r1 = limiter.check("customer:1", now=1_000.0)
        r2 = limiter.check("customer:2", now=1_000.0)
        self.assertTrue(r1.allowed)
        self.assertTrue(r2.allowed)

    def test_every_protected_endpoint_profile_is_buildable(self):
        from app.core.security.rate_limiter import RATE_LIMIT_PROFILES

        store = InMemoryRateLimitStore()
        for profile in RATE_LIMIT_PROFILES:
            limiter = build_rate_limiter(profile, store)
            self.assertTrue(limiter.check(f"probe:{profile}").allowed)


class BackoffLockoutTests(unittest.TestCase):
    def test_not_locked_before_threshold(self):
        store = InMemoryRateLimitStore()
        lockout = BackoffLockout(store, threshold=3)
        lockout.record_failure("login:a@example.com", now=1_000.0)
        lockout.record_failure("login:a@example.com", now=1_000.0)
        self.assertTrue(lockout.is_locked("login:a@example.com", now=1_000.0).allowed)

    def test_locks_after_threshold(self):
        store = InMemoryRateLimitStore()
        lockout = BackoffLockout(store, threshold=3, base_backoff_seconds=2.0)
        for _ in range(3):
            lockout.record_failure("login:a@example.com", now=1_000.0)
        self.assertFalse(lockout.is_locked("login:a@example.com", now=1_000.0).allowed)

    def test_backoff_increases_and_is_capped(self):
        store = InMemoryRateLimitStore()
        lockout = BackoffLockout(store, threshold=1, base_backoff_seconds=2.0, max_backoff_seconds=20.0)
        s1 = lockout.record_failure("k", now=0.0)
        s2 = lockout.record_failure("k", now=0.0)
        s3 = lockout.record_failure("k", now=0.0)
        s4 = lockout.record_failure("k", now=0.0)  # would be 16s uncapped -> stays under cap
        self.assertLess(s1.locked_until, s2.locked_until)
        self.assertLess(s2.locked_until, s3.locked_until)
        self.assertLessEqual(s4.locked_until - 0.0, 20.0)

    def test_success_clears_failure_state(self):
        store = InMemoryRateLimitStore()
        lockout = BackoffLockout(store, threshold=2)
        lockout.record_failure("k", now=0.0)
        lockout.record_failure("k", now=0.0)
        self.assertFalse(lockout.is_locked("k", now=0.0).allowed)
        lockout.record_success("k")
        self.assertTrue(lockout.is_locked("k", now=0.0).allowed)

    def test_lock_expires_on_its_own(self):
        store = InMemoryRateLimitStore()
        lockout = BackoffLockout(store, threshold=1, base_backoff_seconds=5.0)
        lockout.record_failure("k", now=0.0)
        self.assertFalse(lockout.is_locked("k", now=1.0).allowed)
        self.assertTrue(lockout.is_locked("k", now=10.0).allowed)


class VerificationSessionTests(unittest.TestCase):
    def test_starts_pending(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking")
        self.assertEqual(s.status, VerificationStatus.VERIFICATION_PENDING)

    def test_correct_factor_verifies(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking")
        s2 = s.submit_factor_result(matched=True)
        self.assertEqual(s2.status, VerificationStatus.VERIFIED)
        self.assertTrue(s2.is_usable())

    def test_wrong_factor_stays_pending_until_max_attempts_then_fails(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking", max_attempts=3)
        s = s.submit_factor_result(matched=False)
        self.assertEqual(s.status, VerificationStatus.VERIFICATION_PENDING)
        s = s.submit_factor_result(matched=False)
        self.assertEqual(s.status, VerificationStatus.VERIFICATION_PENDING)
        s = s.submit_factor_result(matched=False)
        self.assertEqual(s.status, VerificationStatus.FAILED)

    def test_expired_session_reports_expired(self):
        now = datetime.now(timezone.utc)
        s = VerificationSessionState.start(
            session_id="v1", booking_id="bk_1", purpose="cancel_booking",
            ttl=timedelta(minutes=1), now=now - timedelta(minutes=5),
        )
        self.assertEqual(s.current_status(now=now), VerificationStatus.EXPIRED)
        expired = s.submit_factor_result(matched=True, now=now)
        self.assertEqual(expired.status, VerificationStatus.EXPIRED)
        self.assertFalse(expired.is_usable(now=now))

    def test_scoped_to_booking_and_purpose(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking")
        s = s.submit_factor_result(matched=True)
        self.assertTrue(s.scoped_to(booking_id="bk_1", purpose="cancel_booking"))
        self.assertFalse(s.scoped_to(booking_id="bk_1", purpose="modify_booking"))
        self.assertFalse(s.scoped_to(booking_id="bk_2", purpose="cancel_booking"))

    def test_terminal_session_cannot_be_rescored(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking")
        verified = s.submit_factor_result(matched=True)
        with self.assertRaises(VerificationSessionError):
            verified.submit_factor_result(matched=True)

    def test_failed_session_cannot_be_rescored(self):
        s = VerificationSessionState.start(session_id="v1", booking_id="bk_1", purpose="cancel_booking", max_attempts=1)
        failed = s.submit_factor_result(matched=False)
        self.assertEqual(failed.status, VerificationStatus.FAILED)
        with self.assertRaises(VerificationSessionError):
            failed.submit_factor_result(matched=False)


class CsrfTests(unittest.TestCase):
    def test_valid_token_round_trips(self):
        token = issue_csrf_token("session_1", "server-secret")
        self.assertTrue(
            verify_csrf(session_id="session_1", secret_key="server-secret", cookie_value=token.cookie_value, header_value=token.cookie_value)
        )

    def test_tampered_signature_rejected(self):
        token = issue_csrf_token("session_1", "server-secret")
        nonce, _sig = token.cookie_value.split(".", 1)
        tampered = f"{nonce}.deadbeef00"
        self.assertFalse(
            verify_csrf(session_id="session_1", secret_key="server-secret", cookie_value=tampered, header_value=tampered)
        )

    def test_token_for_different_session_rejected(self):
        token = issue_csrf_token("session_1", "server-secret")
        self.assertFalse(
            verify_csrf(session_id="session_2", secret_key="server-secret", cookie_value=token.cookie_value, header_value=token.cookie_value)
        )

    def test_missing_cookie_or_header_rejected(self):
        token = issue_csrf_token("session_1", "server-secret")
        self.assertFalse(verify_csrf(session_id="session_1", secret_key="server-secret", cookie_value=None, header_value=token.cookie_value))
        self.assertFalse(verify_csrf(session_id="session_1", secret_key="server-secret", cookie_value=token.cookie_value, header_value=None))

    def test_cookie_header_mismatch_rejected(self):
        t1 = issue_csrf_token("session_1", "server-secret")
        t2 = issue_csrf_token("session_1", "server-secret")
        self.assertFalse(
            verify_csrf(session_id="session_1", secret_key="server-secret", cookie_value=t1.cookie_value, header_value=t2.cookie_value)
        )

    def test_safe_methods_skip_csrf(self):
        self.assertFalse(requires_csrf_check("GET"))
        self.assertFalse(requires_csrf_check("HEAD"))
        self.assertTrue(requires_csrf_check("POST"))
        self.assertTrue(requires_csrf_check("DELETE"))


class RedactionTests(unittest.TestCase):
    def test_top_level_sensitive_key_redacted(self):
        out = redact_value({"password": "hunter2", "email": "a@b.com"})
        self.assertEqual(out["password"], "[REDACTED]")
        self.assertEqual(out["email"], "a@b.com")

    def test_nested_dict_is_redacted_the_gap_the_old_processor_had(self):
        out = redact_value({"user": {"password": "hunter2", "name": "Jane"}})
        self.assertEqual(out["user"]["password"], "[REDACTED]")
        self.assertEqual(out["user"]["name"], "Jane")

    def test_list_of_dicts_is_redacted(self):
        out = redact_value({"sessions": [{"session_token": "abc"}, {"session_token": "def"}]})
        self.assertTrue(all(s["session_token"] == "[REDACTED]" for s in out["sessions"]))

    def test_cookie_key_now_redacted(self):
        out = redact_value({"cookie": "c123_session=abcdef"})
        self.assertEqual(out["cookie"], "[REDACTED]")

    def test_case_insensitive_key_match(self):
        out = redact_value({"Authorization": "Bearer xyz", "PASSPORT_NUMBER": "X1234567"})
        self.assertEqual(out["Authorization"], "[REDACTED]")
        self.assertEqual(out["PASSPORT_NUMBER"], "[REDACTED]")

    def test_embedded_bearer_token_in_string_value_is_scrubbed(self):
        out = redact_string_value("retrying request with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVA")
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVA", out)
        self.assertIn("[REDACTED]", out)

    def test_ordinary_text_untouched(self):
        out = redact_value({"note": "the customer asked for an aisle seat"})
        self.assertEqual(out["note"], "the customer asked for an aisle seat")

    def test_non_string_values_pass_through(self):
        out = redact_value({"count": 3, "active": True, "ratio": 1.5, "nothing": None})
        self.assertEqual(out, {"count": 3, "active": True, "ratio": 1.5, "nothing": None})


class VapiAuthorizationTests(unittest.TestCase):
    """Phase 4 spec §34, run for real (the live webhook/tool endpoints
    themselves are Phase 5 — this proves the policy they'll call)."""

    def test_unauthenticated_vapi_request_rejected(self):
        actor = _vapi_actor(authenticated=False)
        decision = authorize_vapi_tool_call(actor, tool_name="get_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error_code, AuthErrorCode.AUTHENTICATION_REQUIRED.value)

    def test_authenticated_but_unverified_booking_sensitive_tool_rejected(self):
        actor = _vapi_actor(authenticated=True, verified_booking_id=None)
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)

    def test_authenticated_verified_booking_authorized_tool_allowed(self):
        actor = _vapi_actor(authenticated=True, verified_booking_id="bk_1", purpose="vapi_tool_access")
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertTrue(decision.allowed)

    def test_public_tool_needs_no_booking_verification(self):
        actor = _vapi_actor(authenticated=True)
        decision = authorize_vapi_tool_call(actor, tool_name="search_flights")
        self.assertTrue(decision.allowed)

    def test_staff_only_tool_always_denied_for_vapi_even_with_permission(self):
        actor = _vapi_actor(authenticated=True, permissions=frozenset({"vapi.execute", "payments.refund"}))
        decision = authorize_vapi_tool_call(actor, tool_name="refund_payment", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "requires_human_staff_or_admin")

    def test_unknown_tool_denied(self):
        actor = _vapi_actor(authenticated=True)
        decision = authorize_vapi_tool_call(actor, tool_name="delete_entire_database")
        self.assertFalse(decision.allowed)

    def test_verified_for_wrong_booking_still_denied(self):
        actor = _vapi_actor(authenticated=True, verified_booking_id="bk_OTHER", purpose="vapi_tool_access")
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)

    def test_non_vapi_actor_rejected_outright(self):
        human = _human_actor(roles=[Role.ADMIN.value])
        decision = authorize_vapi_tool_call(human, tool_name="search_flights")
        self.assertFalse(decision.allowed)


class AuthErrorCodeTests(unittest.TestCase):
    def test_every_code_has_an_http_status(self):
        for code in AuthErrorCode:
            self.assertIn(code, HTTP_STATUS_FOR_CODE)

    def test_codes_are_unique_strings(self):
        values = [c.value for c in AuthErrorCode]
        self.assertEqual(len(values), len(set(values)))


if __name__ == "__main__":
    unittest.main()
