"""Guards that keep the backend usable by a separate browser frontend."""
from scripts.export_openapi import OUTPUT, render


def test_cors_preflight_allows_the_frontend_origin(client):
    res = client.options(
        "/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_is_not_allowed(client):
    res = client.options("/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in res.headers


def test_committed_openapi_contract_is_up_to_date():
    assert OUTPUT.read_text() == render(), "API changed: run `python -m scripts.export_openapi` and commit openapi.json"
