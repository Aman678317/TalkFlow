# GlobalTalk AI — developer workflow
.PHONY: bootstrap dev api web test test-unit test-integration test-realtime verify-ai-stack \
        models migrate lint build docker-up docker-down clean

PY := python3
PIP := pip
export PYTHONPATH := apps/api:.
export MALLOC_ARENA_MAX := 2

## one-command local bootstrap (no Docker required)
bootstrap:
	@bash scripts/bootstrap_full_ai.sh

## download AI model weights into MODEL_CACHE_PATH
models:
	@bash scripts/download_models.sh

## run API + web (dev)
dev:
	@bash scripts/run_dev.sh

api:
	cd apps/api && $(PY) -m uvicorn globaltalk.main:app --reload --port 8000

web:
	cd apps/web && npx vite

## database
migrate:
	cd apps/api && $(PY) -m alembic upgrade head

## tests
test: test-unit test-integration test-realtime
test-unit:
	$(PY) -m pytest tests/unit -q
test-integration:
	$(PY) -m pytest tests/integration -q
test-realtime:
	$(PY) -m pytest tests/realtime -q -m realtime

## frontend
lint:
	cd apps/web && npx tsc -b
build:
	cd apps/web && npx vite build

## ten-repository integration check (section 91)
verify-ai-stack:
	@$(PY) scripts/verify_ai_stack.py

## docker full topology
docker-up:
	docker compose -f infrastructure/docker/docker-compose.yml up --build
docker-down:
	docker compose -f infrastructure/docker/docker-compose.yml down

clean:
	rm -rf data/*.db data/storage apps/web/dist .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
