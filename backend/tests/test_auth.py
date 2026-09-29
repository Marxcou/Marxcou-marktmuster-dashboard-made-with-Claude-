from tests.conftest import login


def test_requires_login(client):
    assert client.get("/api/watchlist").status_code == 401
    assert client.get("/api/sources").status_code == 401


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@dashboard-test.org", "password": "nope"})
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


def test_ensure_admin_refuses_placeholders(client, monkeypatch, caplog):
    from app import bootstrap
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
        monkeypatch.setattr(bootstrap, "get_settings", lambda: type("S", (), {
            "admin_email": "admin@example.com", "admin_password": "change-me-now"})())
        bootstrap.ensure_admin(db)
        assert db.query(User).count() == 0
    assert "Platzhalter" in caplog.text


def test_ensure_admin_warns_on_email_mismatch_and_keeps_password(client, monkeypatch, caplog):
    from app import bootstrap
    from app.db import SessionLocal
    from app.models import User

    monkeypatch.setattr(bootstrap, "get_settings", lambda: type("S", (), {
        "admin_email": "neu@example.org", "admin_password": "another-long-pw"})())
    with SessionLocal() as db:
        old_hash = db.query(User).one().password_hash
        bootstrap.ensure_admin(db)
        assert db.query(User).one().password_hash == old_hash
    assert "neu@example.org" in caplog.text


def test_admin_cli_applies_env_credentials(client, monkeypatch, capsys):
    from app import admin_cli
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "admin_email", "Luca@Example.org")
    monkeypatch.setattr(s, "admin_password", "my-new-long-password")
    monkeypatch.setattr(admin_cli, "get_settings", lambda: s)
    assert admin_cli.main() == 0
    assert "aktualisiert" in capsys.readouterr().out
    login(client, "luca@example.org", "my-new-long-password")


def test_admin_cli_rejects_placeholders(client, monkeypatch, capsys):
    from app import admin_cli

    fake = type("S", (), {"admin_email": "admin@example.com", "admin_password": "change-me-now"})()
    monkeypatch.setattr(admin_cli, "get_settings", lambda: fake)
    assert admin_cli.main() == 1
