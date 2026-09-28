#!/bin/sh
set -e
case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    # Der api-Container besitzt die Migrationen; der Worker wartet, bis das Schema da ist.
    exec python -m app.worker
    ;;
  *) exec "$@" ;;
esac
