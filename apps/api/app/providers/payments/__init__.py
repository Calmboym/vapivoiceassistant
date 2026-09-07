"""
Provider factory: this is the ONLY place in the app that should decide
*which* PaymentProvider implementation to use. PaymentService depends on
the abstract PaymentProvider type (app.providers.payments.base) and gets
a concrete instance from get_payment_provider() — never imports
MockPaymentProvider or StripePaymentProvider directly. That's what makes
PAYMENT_PROVIDER=stripe a config change, not a code change. Mirrors
app/providers/airline/__init__.py exactly — same reasoning, same
lazy-import discipline for the same reason.
"""

from __future__ import annotations

from functools import lru_cache

from app.providers.payments.base import PaymentProvider

# NOTE: get_settings is imported lazily *inside* the function below, not
# at module level — same reason as app/providers/airline/__init__.py's
# NOTE: this __init__.py runs whenever ANYTHING imports a submodule of
# app.providers.payments (Python always executes a package's __init__.py
# first), including app.providers.payments.base and .mock, which are
# deliberately dependency-free so tests/test_payments_core.py can run
# with nothing but the standard library. An eager `from app.core.config
# import get_settings` here would drag pydantic into that import chain.
# `import stripe` is even heavier than that — StripePaymentProvider is
# imported ONLY inside the "stripe" branch below, so selecting
# PAYMENT_PROVIDER=mock (the default) never requires `stripe` to be
# installed at all.


@lru_cache
def get_payment_provider() -> PaymentProvider:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.payment_provider == "mock":
        from app.providers.payments.mock import MockPaymentProvider

        return MockPaymentProvider()
    if settings.payment_provider == "stripe":
        from app.providers.payments.stripe_provider import StripePaymentProvider

        return StripePaymentProvider(
            api_key=settings.stripe_secret_key or "", webhook_secret=settings.stripe_webhook_secret or ""
        )
    raise ValueError(f"Unknown PAYMENT_PROVIDER: {settings.payment_provider}")
