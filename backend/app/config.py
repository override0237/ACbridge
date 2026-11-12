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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
