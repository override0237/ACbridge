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

    # --- trade-group vouches ---
    # A confirmed vouch from a vetted trade group automatically verifies that skill (no extra verifier step).
    trade_group_vouch_auto_verifies: bool = True
    vouch_token_ttl_hours: int = 168            # how long the emailed confirmation link stays valid (7 days)
    vouch_reject_cooldown_days: int = 7         # an artisan cannot re-ask a group that just said no
    # Where the emailed links point. The backend hosts a simple confirmation page, so trade groups (who have no
    # account) can confirm even without the frontend. Set PUBLIC_API_URL to the deployed API address.
    public_api_url: str = "http://localhost:8000"

    # Email: "console" only records messages in memory (SIMULATED, nothing is sent); "smtp" really sends.
    email_mode: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Cooling-off ("probation") after the price is agreed: either side may walk away for free, and no fee or
    # escrow can be paid until it ends. 0 disables it (used by the automated tests).
    probation_hours: int = 24

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
        if self.email_mode == "smtp" and not (self.smtp_host and self.smtp_from):
            raise ValueError("EMAIL_MODE=smtp needs SMTP_HOST and SMTP_FROM")
        if self.environment.lower() == "production" and self.email_mode == "console":
            raise ValueError("EMAIL_MODE=console sends nothing; use smtp in production")
        if self.environment.lower() == "production" and self.payment_provider == "simulated":
            raise ValueError("The simulated payment provider moves no real money and cannot run in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
