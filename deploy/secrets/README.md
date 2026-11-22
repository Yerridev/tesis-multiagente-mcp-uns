# Secretos de despliegue (Docker)

Este directorio es para **archivos sensibles locales** que se montan en los
contenedores. Git lo ignora (`deploy/secrets/*` en `.gitignore`); solo se versiona
este README.

## Qué puede vivir aquí

| Archivo | Uso | Ejemplo de creación |
|---|---|---|
| `mosquitto_passwd` | Usuarios MQTT (backend_reader, ingestor, connector_level, control_level) | `mosquitto_passwd -c mosquitto_passwd backend_reader` (repetir por usuario sin `-c`) |
| `openrouter_api_key` | Clave de OpenRouter (una línea) | `echo "sk-or-..." > openrouter_api_key` |
| `postgres_passwords.env` | Sobreescribir contraseñas por despliegue | solo en entornos con vault |

## Reglas

1. **Nunca** pegar claves en `compose.yaml`, imágenes, documentación ni logs.
2. El backend solo recibe `OPENROUTER_API_KEY` por **variable de entorno**.
3. La clave de OpenRouter que estaba en `backend/appsettings.json` fue eliminada del
   código; **rotarla manualmente en openrouter.ai** (sigue expuesta en el historial de git).
4. Rotación: cambiar el archivo local → `docker compose up -d backend` (sin reconstruir).
5. En el perfil de desarrollo `compose.override.yaml` Mosquitto corre con
   `allow_anonymous true` para no complicar el lab; en producción se usa la
   configuración estricta de `deploy/mosquitto/mosquitto.conf` + `acl`.
