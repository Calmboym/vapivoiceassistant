"""
Central configuration. Every setting is read from the environment (see
.env.example at the repo root) — nothing here is hard-coded, per §49/§52.

`Settings.validate_for_production()` is called once at startup when
APP_ENV=production and raises immediately if anything required is missing,
per §76 ("Fail fast if required production configuration is missing").
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = Field("development", alias="APP_ENV")

    # --- core infra -------------------------------------------------------
    database_url: str = Field("sqlite:///./charter123_dev.db", alias="DATABASE_URL")
    redis_url: Optional[str] = Field(None, alias="REDIS_URL")
    secret_key: str = Field("dev-only-insecure-secret-change-me", alias="SECRET_KEY")
    field_encryption_key: Optional[str] = Field(None, alias="FIELD_ENCRYPTION_KEY")

    # --- Vapi ---------------------------------------------------------------
    vapi_api_key: Optional[str] = Field(None, alias="VAPI_API_KEY")
    vapi_webhook_secret: Optional[str] = Field(None, alias="VAPI_WEBHOOK_SECRET")
    vapi_assistant_id: Optional[str] = Field(None, alias="VAPI_ASSISTANT_ID")
    vapi_phone_number_id: Optional[str] = Field(None, alias="VAPI_PHONE_NUMBER_ID")

    # --- airline provider ---------------------------------------------------
    airline_provider: Literal["mock", "amadeus", "sabre"] = Field("mock", alias="AIRLINE_PROVIDER")
    airline_api_base_url: Optional[str] = Field(None, alias="AIRLINE_API_BASE_URL")
    airline_api_key: Optional[str] = Field(None, alias="AIRLINE_API_KEY")
    airline_api_secret: Optional[str] = Field(None, alias="AIRLINE_API_SECRET")
    airline_client_id: Optional[str] = Field(None, alias="AIRLINE_CLIENT_ID")
    airline_client_secret: Optional[str] = Field(None, alias="AIRLINE_CLIENT_SECRET")
    airline_environment: Optional[str] = Field(None, alias="AIRLINE_ENVIRONMENT")

    # --- payments (Phase 6 Milestone 1) ------------------------------------
    # Mirrors AIRLINE_PROVIDER's mock/real split exactly — see
    # app/providers/payments/__init__.py's factory. "mock" is the default
    # so nothing breaks for anyone who pulls this milestone without
    # setting a single new env var.
    payment_provider: Literal["mock", "stripe"] = Field("mock", alias="PAYMENT_PROVIDER")
    stripe_secret_key: Optional[str] = Field(None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: Optional[str] = Field(None, alias="STRIPE_WEBHOOK_SECRET")

    # --- notifications --------------------------------------------------
    resend_api_key: Optional[str] = Field(None, alias="RESEND_API_KEY")
    twilio_account_sid: Optional[str] = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(None, alias="TWILIO_PHONE_NUMBER")

    # --- web / cors -------------------------------------------------------
    frontend_url: str = Field("http://localhost:3000", alias="FRONTEND_URL")
    cors_origins: str = Field("http://localhost:3000", alias="CORS_ORIGINS")

    # --- auth / admin bootstrap (Phase 4, §16) -----------------------------
    # Never a hard-coded admin/admin account (§16) — bootstrap only runs
    # when explicitly enabled, via `python -m app.db.bootstrap_admin`,
    # and validate_for_production() below refuses to start at all if
    # it's left on in production.
    bootstrap_admin_enabled: bool = Field(False, alias="BOOTSTRAP_ADMIN_ENABLED")
    bootstrap_admin_email: Optional[str] = Field(None, alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: Optional[str] = Field(None, alias="BOOTSTRAP_ADMIN_PASSWORD")

    # --- observability ----------------------------------------------------
    sentry_dsn: Optional[str] = Field(None, alias="SENTRY_DSN")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # --- retention (see §65) ------------------------------------------------
    call_transcript_retention_days: int = Field(90, alias="CALL_TRANSCRIPT_RETENTION_DAYS")
    call_recording_retention_days: int = Field(30, alias="CALL_RECORDING_RETENTION_DAYS")
    audit_log_retention_days: int = Field(365 * 2, alias="AUDIT_LOG_RETENTION_DAYS")
    call_recording_enabled: bool = Field(False, alias="CALL_RECORDING_ENABLED")
    recording_disclosure_message: str = Field(
        "This call may be recorded for quality and training purposes.",
        alias="RECORDING_DISCLOSURE_MESSAGE",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_mock_mode(self) -> bool:
        return self.airline_provider == "mock"

    @model_validator(mode="after")
    def validate_for_production(self) -> "Settings":
        if self.app_env != "production":
            return self
        missing = []
        if self.secret_key == "dev-only-insecure-secret-change-me":
            missing.append("SECRET_KEY")
        if not self.field_encryption_key:
            missing.append("FIELD_ENCRYPTION_KEY (required to encrypt passport numbers at rest)")
        if not self.database_url.startswith("postgresql"):
            missing.append("DATABASE_URL (must be a real PostgreSQL instance in production)")
        if not self.redis_url:
            missing.append("REDIS_URL")
        if not self.vapi_api_key or not self.vapi_webhook_secret:
            missing.append("VAPI_API_KEY / VAPI_WEBHOOK_SECRET")
        if self.airline_provider != "mock" and not self.airline_api_base_url:
            missing.append("AIRLINE_API_BASE_URL")
        if self.payment_provider == "stripe" and (not self.stripe_secret_key or not self.stripe_webhook_secret):
            missing.append("STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET (required when PAYMENT_PROVIDER=stripe)")
        if self.bootstrap_admin_enabled:
            missing.append(
                "BOOTSTRAP_ADMIN_ENABLED must be false in production (§16) — "
                "run `python -m app.db.bootstrap_admin` once by hand instead, then unset it"
            )
        if missing:
            raise ValueError(
                "APP_ENV=production but required configuration is missing: " + ", ".join(missing)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
