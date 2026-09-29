#!/bin/sh
# Aktualisiert den Server auf den Stand von main: sichern, holen, bauen, neu starten, prüfen.
# Aufruf im Projektordner: ./deploy/update.sh
set -eu
cd "$(dirname "$0")/.."
. ./deploy/lib.sh
echo "1/4 Sicherung ..."
if [ -x deploy/backup.sh ] && $COMPOSE ps --status running api 2>/dev/null | grep -q api; then
  ./deploy/backup.sh || echo "Warnung: Sicherung fehlgeschlagen, mache trotzdem weiter."
fi
echo "2/4 Neuen Stand holen ..."
git pull --ff-only
echo "3/4 Bauen und starten ..."
$COMPOSE up -d --build
echo "4/4 Warten auf api ..."
i=0
until [ "$($COMPOSE ps --format '{{.Health}}' api 2>/dev/null)" = "healthy" ]; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "api wurde nicht gesund. Log: $COMPOSE logs api --tail 50" >&2; exit 1; }
  sleep 5
done
docker image prune -f >/dev/null
echo "Fertig. Stand: $(git rev-parse --short HEAD)"
