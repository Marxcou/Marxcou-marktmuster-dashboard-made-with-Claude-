#!/bin/sh
# Nächtliche Sicherung der SQLite-Datenbank (Konten, Watchlists, Nachrichten, Analysen).
# Nutzt die SQLite-Sicherungsfunktion, ist also auch bei laufendem Betrieb konsistent.
# Ablage: /opt/marktmuster-backups (Host), 14 Tage lang. Aufruf: ./deploy/backup.sh
set -eu
cd "$(dirname "$0")/.."
. ./deploy/lib.sh
DEST="${BACKUP_DIR:-/opt/marktmuster-backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
umask 077
$COMPOSE exec -T api python - <<'PY' > "$DEST/marktmuster-$STAMP.db"
import os, sqlite3, sys, tempfile
url = os.environ.get("DATABASE_URL", "sqlite:////data/marktmuster.db")
path = url.split("sqlite:///", 1)[1]
src = sqlite3.connect(path)
with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
    dst = sqlite3.connect(tmp.name)
    src.backup(dst)
    dst.close()
    sys.stdout.buffer.write(open(tmp.name, "rb").read())
PY
gzip -f "$DEST/marktmuster-$STAMP.db"
find "$DEST" -name 'marktmuster-*.db.gz' -mtime +"$KEEP_DAYS" -delete
echo "Sicherung: $DEST/marktmuster-$STAMP.db.gz"
