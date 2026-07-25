#!/bin/sh
set -e

python <<'PYEOF'
import os
import sys
import time

import psycopg2

host = os.environ.get("DB_HOST", "localhost")
port = os.environ.get("DB_PORT", "5432")
name = os.environ.get("DB_NAME", "sinkscope")
user = os.environ.get("DB_USER", "sinkscope")
password = os.environ.get("DB_PASSWORD", "sinkscope")

for _ in range(30):
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=name, user=user, password=password)
        conn.close()
        sys.exit(0)
    except psycopg2.OperationalError:
        time.sleep(2)

sys.exit("database not reachable after 60s")
PYEOF

exec "$@"
