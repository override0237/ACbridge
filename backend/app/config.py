"""Central configuration. Every secret / environment-specific value comes from env vars."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me-before-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://acbridge:acbridge@localhost:5432/acbridge"

    jwt_secret: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    # Browser origins allowed to call the API (your frontend's dev/prod URLs), comma-separated.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    # Service area: the platform only matches within these towns (lower-case, comma-separated).
    supported_towns: str = "buea,limbe"

    # Community proof required before a SKILL verification can be approved.
    min_endorsements_for_skill_verification: int = 2

    rate_limit_enabled: bool = True

    evidence_upload_dir: str = "uploads"
    max_evidence_bytes: int = 5 * 1024 * 1024

    # Reputation prior (see reputation_service). m = evidence threshold, C = platform average.
    reputation_min_evidence: int = 10
    reputation_platform_average: float = 4.0

    # Platform revenue. Fixed-price jobs: the artisan pays COMMISSION_RATE_BPS basis points (500 = 5%) of the agreed
    # price, never less than COMMISSION_MIN. Inspection jobs: the artisan pays one flat INSPECTION_ASSIGNMENT_FEE.
    commission_rate_bps: int = 500
    commission_min: int = 300
    inspection_assignment_fee: int = 1000

    # Cooling-off ("probation") after the price is agreed: either side may walk away for free, and no fee or
    # escrow can be paid until it ends. 0 disables it (used by the automated tests).
    probation_hours: int = 24

    # WHO PAYS THE COMMISSION, AND WHEN.
    #   artisan_upfront : (default) the artisan pays the commission before the job is assigned (see job_service).
    #   customer_split  : the customer pays the full agreed price; the commission is cut from that payment and booked as
    #                     platform revenue the moment it succeeds, the rest waits as the artisan's pending payout until the
    #                     job is completed. The artisan pays nothing up front; contact details unlock after payment.
    commission_model: str = "artisan_upfront"

    # Dispute window after completion (hours) and how long a proposed price stays valid (0 = never expires).
    dispute_window_hours: int = 48
    quote_ttl_hours: int = 24

    # Shared secret used to sign payment-provider webhooks (HMAC-SHA256 of the raw body, hex, header X-Signature).
    webhook_secret: str = "dev-only-webhook-secret-change-me"

    # Per-phone limit on starting payments.
    pay_rate_limit_calls: int = 5
    pay_rate_limit_window_seconds: int = 600

    # Only "simulated" exists: no real money moves. Real MTN MoMo / Orange Money needs provider accounts.
    payment_provider: str = "simulated"

    # HONESTY FLAG: no real-world identity/skill assessment happens in this MVP.
    verification_mode: str = "SIMULATED"

    @property
    def supported_town_set(self) -> frozenset[str]:
        return frozenset(t.strip().lower() for t in self.supported_towns.split(",") if t.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _refuse_insecure_secret_in_production(self) -> "Settings":
        if self.environment.lower() == "production" and self.jwt_secret == _INSECURE_DEFAULT_SECRET:
            raise ValueError("JWT_SECRET must be set to a strong random value in production")
        if self.environment.lower() == "production" and self.webhook_secret == "dev-only-webhook-secret-change-me":
            raise ValueError("WEBHOOK_SECRET must be set to a strong random value in production")
        if self.commission_model not in ("artisan_upfront", "customer_split"):
            raise ValueError("COMMISSION_MODEL must be 'artisan_upfront' or 'customer_split'")
        if self.environment.lower() == "production" and self.payment_provider == "simulated":
            raise ValueError("The simulated payment provider moves no real money and cannot run in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
