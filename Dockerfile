FROM node:20-alpine AS web-builder
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/services/api:/app/ai:/app \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt /app/services/api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/api/requirements.txt

COPY ai /app/ai
COPY services /app/services
COPY alembic.ini /app/alembic.ini
COPY .antideploy.json /app/.antideploy.json
COPY start.sh /app/start.sh

COPY --from=web-builder /web/dist /app/apps/web/dist

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
