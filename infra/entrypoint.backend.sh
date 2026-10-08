#!/bin/sh
# Backend container entrypoint.
#
# Two jobs before handing over to the real command:
#
#   1. Wait for Postgres. compose's `depends_on: service_healthy` covers the
#      first boot, but a worker restarting while the database restarts is not
#      covered by it, so the wait lives here too.
#   2. Run migrations -- but only where RUN_MIGRATIONS is set. The backend
#      service sets it; the worker and beat do not. Three containers starting
#      together would otherwise run `migrate` concurrently against the same
#      database, and whichever lost the race would exit non-zero.
set -eu

wait_for_database() {
    # No DATABASE_URL means SQLite, which needs no waiting.
    [ -n "${DATABASE_URL:-}" ] || return 0
    case "$DATABASE_URL" in
        postgres*) ;;
        *) return 0 ;;
    esac

    attempt=1
    max_attempts="${DB_WAIT_ATTEMPTS:-60}"

    while [ "$attempt" -le "$max_attempts" ]; do
        # Asks Django itself rather than pg_isready: this proves the
        # credentials, the database name and the driver all work, not merely
        # that something is listening on the port.
        if python -c '
import sys
from django.db import connection
import django

django.setup()
try:
    connection.ensure_connection()
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
' 2>/dev/null; then
            return 0
        fi
        [ "$attempt" -eq 1 ] && echo "entrypoint: waiting for the database..."
        attempt=$((attempt + 1))
        sleep 1
    done

    echo "entrypoint: database did not become reachable in ${max_attempts}s" >&2
    exit 1
}

wait_for_database

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "entrypoint: applying migrations"
    python manage.py migrate --noinput
fi

# exec, so the command replaces this shell as PID 1 and receives SIGTERM
# directly. Without it, docker stop would wait out the full grace period and
# then kill Celery mid-task.
exec "$@"
