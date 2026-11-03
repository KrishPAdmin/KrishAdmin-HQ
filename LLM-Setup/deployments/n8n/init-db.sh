#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$POSTGRES_APP_PASSWORD" <<'SQL'
CREATE ROLE n8n_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE n8n TO n8n_app;
GRANT ALL ON SCHEMA public TO n8n_app;
SQL
