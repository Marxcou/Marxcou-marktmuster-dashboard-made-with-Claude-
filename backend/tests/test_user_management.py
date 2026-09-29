import pytest

from app.config import get_settings
from tests.conftest import login

H = "X-CSRF-Token"


def _change(client, csrf, current, new):
    body = {"current_password": current, "new_password": new}
    return client.post("/api/auth/change-password", json=body, headers={H: csrf})


def _create(client, csrf, email="f@example.com", **kw):
    r = client.post("/api/users", json={"email": email, "display_name": "Freund", **kw}, headers={H: csrf})
    assert r.status_code == 201, r.text
    return r.json()




@pytest.fixture()
def admin_csrf(client):
    return login(client)


def test_create_generates_temporary_password_and_requires_change(client, admin_csrf):
    created = _create(client, admin_csrf)
    assert len(created["temporary_password"]) >= 10
    assert created["must_change_password"] is True and created["is_active"] is True
    assert "password_hash" not in created
    listed = client.get("/api/users").json()
    assert all("password" not in u and "temporary_password" not in u for u in listed)
    client.post("/api/auth/logout", headers={H: admin_csrf})
    csrf = login(client, "f@example.com", created["temporary_password"])
    me = client.get("/api/auth/me").json()
    assert me["user"]["must_change_password"] is True
    assert client.get("/api/watchlist").status_code == 403  # gesperrt bis zum Passwortwechsel
    assert client.get("/api/sources").status_code == 403
    bad = _change(client, csrf, "falsch-falsch", "neues-passwort-1")
    assert bad.status_code == 400
    short = _change(client, csrf, created["temporary_password"], "kurz")
    assert short.status_code == 422
    same = _change(client, csrf, created["temporary_password"], created["temporary_password"])
    assert same.status_code == 400
    ok = _change(client, csrf, created["temporary_password"], "neues-passwort-1")
    assert ok.status_code == 204
    assert client.get("/api/watchlist").status_code == 200
    assert client.get("/api/auth/me").json()["user"]["must_change_password"] is False
    client.post("/api/auth/logout", headers={H: csrf})
    old = {"email": "f@example.com", "password": created["temporary_password"]}
    assert client.post("/api/auth/login", json=old).status_code == 401
    login(client, "f@example.com", "neues-passwort-1")


def test_explicit_password_and_duplicate_email(client, admin_csrf):
    created = _create(client, admin_csrf, password="ein-langes-passwort")
    assert created["temporary_password"] == "ein-langes-passwort"
    r = client.post("/api/users", json={"email": "F@example.com", "display_name": "x"}, headers={H: admin_csrf})
    assert r.status_code == 409


def test_disable_ends_sessions_and_blocks_login_then_reenable(client, admin_csrf):
    created = _create(client, admin_csrf, password="ein-langes-passwort")
    uid = created["id"]
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as friend:
        login(friend, "f@example.com", "ein-langes-passwort")
        assert friend.get("/api/auth/me").status_code == 200
        r = client.patch(f"/api/users/{uid}", json={"is_active": False}, headers={H: admin_csrf})
        assert r.status_code == 200 and r.json()["is_active"] is False
        assert friend.get("/api/auth/me").status_code == 401  # Sitzung beendet
        blocked = friend.post("/api/auth/login", json={"email": "f@example.com", "password": "ein-langes-passwort"})
        assert blocked.status_code == 403 and "gesperrt" in blocked.json()["detail"]
        wrong = friend.post("/api/auth/login", json={"email": "f@example.com", "password": "falsch-falsch-1"})
        assert wrong.status_code == 401  # gesperrtes Konto verrät sich nicht ohne richtiges Passwort
        client.patch(f"/api/users/{uid}", json={"is_active": True}, headers={H: admin_csrf})
        login(friend, "f@example.com", "ein-langes-passwort")


def test_reset_password_ends_sessions_and_forces_change(client, admin_csrf):
    created = _create(client, admin_csrf, password="ein-langes-passwort")
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as friend:
        login(friend, "f@example.com", "ein-langes-passwort")
        r = client.post(f"/api/users/{created['id']}/reset-password", headers={H: admin_csrf})
        assert r.status_code == 200
        temp = r.json()["temporary_password"]
        assert friend.get("/api/auth/me").status_code == 401
        old = {"email": "f@example.com", "password": "ein-langes-passwort"}
        assert friend.post("/api/auth/login", json=old).status_code == 401
        login(friend, "f@example.com", temp)
        assert friend.get("/api/auth/me").json()["user"]["must_change_password"] is True
    assert client.post("/api/users/9999/reset-password", headers={H: admin_csrf}).status_code == 404


def test_cannot_lock_out_last_admin_or_self(client, admin_csrf):
    me = client.get("/api/auth/me").json()["user"]
    for body in ({"is_active": False}, {"role": "user"}):
        assert client.patch(f"/api/users/{me['id']}", json=body, headers={H: admin_csrf}).status_code == 409
    second = _create(client, admin_csrf, "z@example.com", role="admin")
    r = client.patch(f"/api/users/{second['id']}", json={"is_active": False}, headers={H: admin_csrf})
    assert r.status_code == 200


def test_non_admin_gets_403_on_all_admin_endpoints(client, admin_csrf):
    created = _create(client, admin_csrf, password="ein-langes-passwort")
    client.post("/api/auth/logout", headers={H: admin_csrf})
    csrf = login(client, "f@example.com", "ein-langes-passwort")
    _change(client, csrf, "ein-langes-passwort", "anderes-passwort-1")
    uid = created["id"]
    new = {"email": "n@example.com", "display_name": "n"}
    calls = [("get", "/api/users", None), ("post", "/api/users", new),
             ("patch", f"/api/users/{uid}", {"is_active": False}),
             ("post", f"/api/users/{uid}/reset-password", None)]
    for method, url, body in calls:
        r = getattr(client, method)(url, headers={H: csrf}, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, url)


def test_unauthenticated_admin_endpoints_401(client):
    assert client.get("/api/users").status_code == 401
    assert client.post("/api/users/1/reset-password").status_code == 401


def test_no_endpoint_returns_secrets(client, admin_csrf, monkeypatch):
    """Schlüssel bleiben serverseitig: kein GET (auch Admin) zeigt einen konfigurierten Geheimwert."""
    s = get_settings()
    secrets_ = {}
    for name in ("alpaca_api_key_id", "alpaca_api_secret_key", "finnhub_api_key", "stooq_api_key", "openfigi_api_key",
                 "marketaux_api_key", "alphavantage_api_key", "anthropic_api_key", "session_secret", "admin_password"):
        secrets_[name] = f"SECRET-{name}-9f8e7d6c"
        monkeypatch.setattr(s, name, secrets_[name])
    created = _create(client, admin_csrf)
    from app.main import app
    paths = sorted(p for p, ops in app.openapi()["paths"].items() if "get" in ops and "{" not in p)
    assert "/api/users" in paths and "/api/sources" in paths
    bodies = [client.get(p).text for p in paths]
    bodies += [client.get("/api/sentiment/status").text]
    joined = "\n".join(bodies) + created["email"]
    for name, value in secrets_.items():
        assert value not in joined, name
    assert "password_hash" not in joined and "$argon2" not in joined
