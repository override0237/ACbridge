from app.models import User
from app.security.authentication import hash_password, verify_password
from app.security.rate_limit import reset_rate_limits
from tests.helpers import PASSWORD


def test_successful_registration_and_login(client):
    res = client.post("/auth/register", json={"phone": "670 11 22 34", "password": PASSWORD, "role": "CUSTOMER"})
    assert res.status_code == 201
    body = res.json()
    assert body["phone"] == "+237670112234"        # normalised to one canonical form
    assert "password" not in body and "password_hash" not in body

    login = client.post("/auth/login", json={"phone": "+237670112234", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["access_token"] and login.json()["role"] == "CUSTOMER"


def test_password_is_stored_as_argon2id(client, session_factory):
    client.post("/auth/register", json={"phone": "670000001", "password": PASSWORD, "role": "CUSTOMER"})
    with session_factory() as db:
        stored = db.query(User).one().password_hash
    assert stored.startswith("$argon2id$") and PASSWORD not in stored
    assert verify_password(PASSWORD, stored) and not verify_password("wrong", stored)


def test_duplicate_phone_rejected_even_in_a_different_format(client):
    first = client.post("/auth/register", json={"phone": "670000002", "password": PASSWORD, "role": "CUSTOMER"})
    second = client.post("/auth/register", json={"phone": "+237 670 000 002", "password": PASSWORD, "role": "ARTISAN"})
    assert first.status_code == 201
    assert second.status_code == 409


def test_invalid_login_is_rejected_without_revealing_which_part_was_wrong(client):
    client.post("/auth/register", json={"phone": "670000003", "password": PASSWORD, "role": "CUSTOMER"})
    wrong_password = client.post("/auth/login", json={"phone": "670000003", "password": "nope-nope-nope"})
    unknown_phone = client.post("/auth/login", json={"phone": "670999999", "password": PASSWORD})
    assert wrong_password.status_code == unknown_phone.status_code == 401
    assert wrong_password.json() == unknown_phone.json()


def test_cannot_self_register_as_verifier_or_admin(client):
    for role in ("VERIFIER", "ADMIN"):
        res = client.post("/auth/register", json={"phone": "670000004", "password": PASSWORD, "role": role})
        assert res.status_code == 422


def test_protected_endpoint_needs_valid_token(client):
    assert client.post("/service-requests", json={}).status_code == 401
    assert client.post("/service-requests", json={}, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_comes_from_database_not_token(world):
    customer = world.user("CUSTOMER")
    res = world.client.post("/artisans", headers=customer.headers, json={"full_name": "Fake", "location": "Buea"})
    assert res.status_code == 403   # a customer cannot create artisan profiles


def test_rate_limit_blocks_brute_force_login(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    reset_rate_limits()
    codes = [client.post("/auth/login", json={"phone": "670123123", "password": "wrongwrong"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    reset_rate_limits()
