# Betrieb auf einem Server

Für den Dauerbetrieb auf einem gemieteten Server (empfohlen: Hetzner CX23, Ubuntu 24.04, Docker). Die Schritt-für-Schritt-Anleitung von der Servermiete bis zum ersten Login steht in der Server-Anleitung des Projekts; dieses Dokument beschreibt, was im Repository dafür vorhanden ist und wie man den Server betreibt.

**Geheimnisse:** API-Schlüssel, `SESSION_SECRET` und `ADMIN_PASSWORD` stehen nur in der `.env` auf dem Server (`chmod 600`). Sie liegen nie im Repository, nie in einem Image und nie in Logs (siehe `backend/app/log_redaction.py`). Mit `APP_ENV=production` startet die API nicht, solange `SESSION_SECRET` (mindestens 32 Zeichen) oder `ADMIN_PASSWORD` noch den Beispielwert haben.

## Zwei Betriebsarten

| | Weg A: Tailscale | Weg B: öffentliche Adresse mit HTTPS |
|---|---|---|
| Erreichbar für | Geräte im privaten Tailscale-Netz | jeder mit der Adresse (Login nötig) |
| Start | `docker compose up -d --build` | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |
| Adresse | `http://<Tailscale-IP>:8080` | `https://<DOMAIN>` |
| `.env` | `COOKIE_SECURE=false`, `DOMAIN` leer | `COOKIE_SECURE=true`, `DOMAIN=meindashboard.de` |
| Firewall | nur SSH (22) | SSH (22), 80, 443 |

Die Skripte in `deploy/` erkennen die Betriebsart selbst: Steht `DOMAIN` in der `.env`, nutzen sie die Produktionsdatei (`deploy/lib.sh`).

### Weg B im Detail

1. A-Eintrag der Domain auf die Server-IP setzen, Ports 80 und 443 in der Firewall freigeben.
2. In `.env`: `APP_ENV=production`, `COOKIE_SECURE=true`, `DOMAIN=...`, neues `SESSION_SECRET`, starkes `ADMIN_PASSWORD`.
3. Starten wie in der Tabelle. Caddy (`deploy/Caddyfile`) holt und erneuert das Zertifikat selbst (Let's Encrypt), leitet HTTP auf HTTPS um und setzt Sicherheits-Header (HSTS, `nosniff`, `X-Frame-Options`, `Referrer-Policy`). Zertifikate liegen im Volumen `caddy_data`, damit sie Neustarts überstehen.
4. Die App hat in dieser Betriebsart keinen Host-Port; nur Caddy ist von außen erreichbar.

**Cookies und CSRF:** Das Sitzungs-Cookie ist `HttpOnly`, `SameSite=Lax` und mit `COOKIE_SECURE=true` nur über HTTPS gültig. Jede ändernde Anfrage braucht zusätzlich den CSRF-Token im Header `X-CSRF-Token` (`backend/app/deps.py`). Ohne HTTPS (Weg A) muss `COOKIE_SECURE=false` bleiben, sonst kann man sich nicht anmelden.

**Achtung Docker und Firewall:** Docker umgeht `ufw`. Verlasse dich deshalb auf die Firewall des Anbieters (Hetzner), nicht auf `ufw`.

## Aktualisieren

```bash
cd /opt/marktmuster
./deploy/update.sh
```

Das Skript sichert die Datenbank, holt `main` (`git pull --ff-only`), baut neu, startet neu, wartet auf eine gesunde API und räumt alte Images auf. Datenbank-Migrationen laufen beim Start der API automatisch (`alembic upgrade head`). Bricht `git pull` ab, weil auf dem Server Dateien geändert wurden, dort nichts überschreiben, sondern die Änderung prüfen.

## Sicherung

- **Nächtlich:** `sudo ./deploy/install-cron.sh` richtet einmalig einen Cron-Eintrag ein (03:15 Uhr Serverzeit). `deploy/backup.sh` erzeugt mit der SQLite-Sicherungsfunktion eine konsistente Kopie (auch bei laufendem Betrieb), komprimiert sie nach `/opt/marktmuster-backups/marktmuster-<Zeitstempel>.db.gz` (nur für `root` lesbar) und löscht Sicherungen, die älter als 14 Tage sind (`BACKUP_KEEP_DAYS`, `BACKUP_DIR` anpassbar). Log: `/var/log/marktmuster-backup.log`.
- **Manuell:** `./deploy/backup.sh`
- **Prüfen:** `ls -lh /opt/marktmuster-backups/` (jede Nacht eine neue Datei, Größe plausibel)
- **Wiederherstellen:** `./deploy/restore.sh /opt/marktmuster-backups/marktmuster-XXXX.db.gz`. Das Skript fragt nach, stoppt API und Worker, legt die alte Datenbank als `marktmuster.db.vor-restore` im Volumen beiseite, spielt die Sicherung ein und startet neu.
- Die Sicherung enthält Konten (Passwort-Hashes), Watchlists, Nachrichten und Analysen, aber **nicht** die `.env`. Bewahre die `.env` getrennt und sicher auf (z. B. im Passwortmanager).
- Zusätzlich sichern die Hetzner-Backups den ganzen Server. Sicherungen auf demselben Server schützen nicht vor dessen Verlust: gelegentlich eine Kopie auf den eigenen PC holen, z. B. `scp root@<server>:/opt/marktmuster-backups/marktmuster-XXXX.db.gz .`

## Alltag

| Aufgabe | Befehl (im Projektordner) |
|---|---|
| Status | `docker compose ps` |
| Log der API | `docker compose logs api --tail 100` |
| Muster-Backtest (einmalig, dauert) | `docker compose run --rm worker python -m app.backtest_job` |
| Neustart | `docker compose restart` |
| Speicher, Platz | `free -h`, `df -h`, `docker system df` |

Bei Weg B vor jedem `docker compose` die Optionen `-f docker-compose.yml -f docker-compose.prod.yml` ergänzen.

Alle Dienste starten nach einem Neustart des Servers von selbst (`restart: unless-stopped`).

## Vor dem Einladen von Freunden

Nutzungsbedingungen der kostenlosen Datentarife prüfen (Alpaca, Finnhub, Marketaux, RSS-Feeds); das Claude-Budget (`CLAUDE_MONTHLY_BUDGET_USD`) gilt für alle Nutzer zusammen. Der Hinweis "keine Anlageberatung" steht auf jeder Seite.
