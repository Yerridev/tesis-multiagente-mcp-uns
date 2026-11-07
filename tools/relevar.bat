@echo off
cd /d "%~dp0\.."
docker cp tools\relevar.sql mcp-timescaledb:/tmp/relevar.sql > tools\relevar.out 2>&1
docker exec mcp-timescaledb sh -c "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -f /tmp/relevar.sql" >> tools\relevar.out 2>&1
docker ps --format "{{.Names}} | {{.Status}}" >> tools\relevar.out 2>&1
exit
