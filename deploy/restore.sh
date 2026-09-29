#!/bin/sh
# Spielt eine Sicherung ein. Aufruf: ./deploy/restore.sh /opt/marktmuster-backups/marktmuster-XXXX.db.gz
# Die aktuelle Datenbank wird vorher als marktmuster.db.vor-restore im Volumen beiseitegelegt.
set -eu
[ $# -eq 1 ] && [ -f "$1" ] || { echo "Aufruf: $0 <sicherung.db.gz>" >&2; exit 1; }
cd "$(dirname "$0")/.."
. ./deploy/lib.sh
printf 'Die aktuelle Datenbank wird ersetzt. Fortfahren? (ja/nein) '
read -r answer
[ "$answer" = "ja" ] || { echo "Abgebrochen."; exit 1; }
$COMPOSE stop worker api
gunzip -c "$1" | $COMPOSE run --rm --no-deps -T api sh -c '
  cp /data/marktmuster.db /data/marktmuster.db.vor-restore 2>/dev/null || true
  rm -f /data/marktmuster.db-wal /data/marktmuster.db-shm
  cat > /data/marktmuster.db'
$COMPOSE up -d api worker
echo "Wiederhergestellt aus $1."
