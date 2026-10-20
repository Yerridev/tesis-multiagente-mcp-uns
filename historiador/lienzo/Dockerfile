# Lienzo vivo MCC-09: compila el frontend (React) y lo sirve con el backend (FastAPI).
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./lienzo/backend/
COPY --from=web /web/dist ./lienzo/frontend/dist
ENV PYTHONUNBUFFERED=1 MCP_DIR=/app/mcp_servidor STATIC_DIR=/app/lienzo/frontend/dist
WORKDIR /app/lienzo/backend
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
