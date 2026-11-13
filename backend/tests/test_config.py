import pytest
from pydantic import ValidationError

from app.config import Settings

SECRET = "x" * 40


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_hosting_provider_database_urls_use_the_psycopg_driver():
    assert make(database_url="postgres://u:p@host/db").database_url == "postgresql+psycopg://u:p@host/db"
    assert make(database_url="postgresql://u:p@host/db?sslmode=require").database_url == \
        "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert make(database_url="postgresql+psycopg://u:p@host/db").database_url == "postgresql+psycopg://u:p@host/db"
    assert make(database_url="sqlite://").database_url == "sqlite://"


def test_default_secret_only_allowed_in_local_development():
    make(environment="development")                                   # fine locally
    for env in ("demo", "staging", "production"):
        with pytest.raises(ValidationError):
            make(environment=env)                                     # a public demo must set JWT_SECRET
    make(environment="demo", jwt_secret=SECRET)


def test_production_refuses_simulated_money_and_email():
    with pytest.raises(ValidationError):
        make(environment="production", jwt_secret=SECRET)             # simulated payments + console e-mail
    with pytest.raises(ValidationError):
        make(environment="production", jwt_secret=SECRET, email_mode="smtp", smtp_host="h", smtp_from="a@b.co")
    # a public DEMO may use the simulators (and is clearly labelled SIMULATED in every response)
    make(environment="demo", jwt_secret=SECRET)


def test_smtp_mode_needs_host_and_sender():
    with pytest.raises(ValidationError):
        make(email_mode="smtp")
