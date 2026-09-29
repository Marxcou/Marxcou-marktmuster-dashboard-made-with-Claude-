# Gemeinsame Auswahl der Compose-Dateien: mit DOMAIN in .env gilt Weg B (Caddy + HTTPS), sonst Weg A.
if grep -q '^DOMAIN=.\+' .env 2>/dev/null; then
  COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
else
  COMPOSE="docker compose"
fi
