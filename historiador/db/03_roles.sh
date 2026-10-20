#!/bin/bash
# Rol de SOLO LECTURA para el servidor MCP: los agentes de IA nunca pueden escribir en el historiador.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mcp_lector') THEN
            CREATE ROLE mcp_lector LOGIN PASSWORD '${MCP_READER_PASSWORD}';
        END IF;
    END
    \$\$;
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO mcp_lector;
    GRANT USAGE ON SCHEMA public TO mcp_lector;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_lector;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_lector;
EOSQL
