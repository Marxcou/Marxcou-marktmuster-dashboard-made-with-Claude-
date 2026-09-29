#!/bin/sh
# Richtet die nächtliche Sicherung ein (03:15 Uhr Serverzeit). Einmal als root ausführen.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cat > /etc/cron.d/marktmuster-backup <<CRON
15 3 * * * root cd $DIR && ./deploy/backup.sh >> /var/log/marktmuster-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/marktmuster-backup
echo "Nächtliche Sicherung eingerichtet (Log: /var/log/marktmuster-backup.log)."
