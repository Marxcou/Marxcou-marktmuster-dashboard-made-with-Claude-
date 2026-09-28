from tests.conftest import login


def test_requires_login(client):
    assert client.get("/api/watchlist").status_code == 401
    assert client.get("/api/sources").status_code == 401


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401


def test_csrf_enforced_and_invite_only(client):
    csrf = login(client)
    body = {"email": "u@example.com", "display_name": "U", "password": "long-enough-pw"}
    assert client.post("/api/users", json=body).status_code == 403  # kein CSRF-Token
    assert client.post("/api/users", json=body, headers={"X-CSRF-Token": csrf}).status_code == 201
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    csrf2 = login(client, "u@example.com", "long-enough-pw")
    r = client.post("/api/users", json={**body, "email": "x@example.com"}, headers={"X-CSRF-Token": csrf2})
    assert r.status_code == 403  # normale Nutzer dürfen keine Konten anlegen


def test_no_open_registration(client):
    body = {"email": "a@b.de", "display_name": "A", "password": "long-enough-pw"}
    assert client.post("/api/users", json=body).status_code == 401
