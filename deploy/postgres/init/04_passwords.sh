#!/bin/bash
# Contraseñas de los usuarios de aplicación desde variables de entorno.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	ALTER ROLE ingestor WITH PASSWORD '${INGESTOR_PASSWORD:-ingestor_cambiar}';
	ALTER ROLE backend_ro WITH PASSWORD '${BACKEND_RO_PASSWORD:-lector_cambiar}';
	ALTER ROLE mcp_reader WITH PASSWORD '${BACKEND_RO_PASSWORD:-lector_cambiar}';
EOSQL
echo "[init] contraseñas de aplicación configuradas (ingestor, backend_ro, mcp_reader)"
