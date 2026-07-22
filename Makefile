.PHONY: up migrate collect load marts report demo test lint

up:
	docker compose up -d --wait postgres
	@test -f .env || cp .env.example .env

migrate:
	uv run alembic upgrade head

collect:
	uv run python -m pipeline collect

load:
	uv run python -m pipeline load

marts:
	uv run python -m pipeline marts

report:
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/report.ipynb

demo: up migrate collect load marts report
	@echo "Done: fresh data in Postgres, charts in docs/img/"

test:
	uv run pytest -q

lint:
	uv run ruff check .
