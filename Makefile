.PHONY: dev test lint migrate seed validate fmt up down

up:
	docker compose up -d

down:
	docker compose down

dev:
	source .venv/bin/activate && uvicorn apps.api.main:app --reload &
	cd apps/web && npm run dev &
	source .venv/bin/activate && dramatiq apps.worker.main &

test:
	source .venv/bin/activate && pytest tests/

lint:
	source .venv/bin/activate && ruff check apps tests
	source .venv/bin/activate && mypy apps tests
	cd apps/web && npm run lint
	cd apps/web && npx tsc --noEmit

fmt:
	source .venv/bin/activate && ruff format apps tests

migrate:
	source .venv/bin/activate && alembic upgrade head

seed:
	source .venv/bin/activate && python seed.py


validate:
	source .venv/bin/activate && python run_synthetic_validation.py
