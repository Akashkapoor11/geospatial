.PHONY: install run test test-v lint format typecheck check migrate migrate-new docker-up docker-down docker-logs generate-sample clean

# ── Development setup ─────────────────────────────────────────────────────────

install:
	pip install -r requirements-dev.txt

# ── Run the API locally ───────────────────────────────────────────────────────

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	pytest --cov=app --cov-report=term-missing -q

test-v:
	pytest --cov=app --cov-report=term-missing -v

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	ruff check .

format:
	ruff check . --fix
	black .

format-check:
	black --check .
	ruff check .

typecheck:
	mypy app

# Run all quality checks in sequence (matches CI)
check: lint format-check typecheck test

# ── Database migrations ───────────────────────────────────────────────────────

migrate:
	alembic upgrade head

migrate-new:
	@read -p "Migration description: " msg; alembic revision --autogenerate -m "$$msg"

migrate-down:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

# ── Docker ────────────────────────────────────────────────────────────────────

docker-up:
	docker compose up --build

docker-up-d:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

# ── Sample data ───────────────────────────────────────────────────────────────

generate-sample:
	python scripts/generate_sample_shapefile.py

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f .coverage coverage.xml geospatial_api.db
	rm -rf htmlcov .pytest_cache .mypy_cache .ruff_cache
