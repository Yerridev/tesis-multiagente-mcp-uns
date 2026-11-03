@echo off
cd /d "%~dp0"
docker compose -f compose.yaml -f compose.override.yaml up -d --build connector-nivel > reconstruir-nivel.log 2>&1
exit
