.PHONY: up down build logs restart migrate revision test lint format create-admin seed reset-dev

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

restart:
	docker compose restart

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(name)"

test:
	docker compose exec api pytest

lint:
	docker compose exec api ruff check .
	docker compose exec dashboard npm run lint

format:
	docker compose exec api ruff format .
	docker compose exec dashboard npm run format

create-admin:
	docker compose exec api python -m app.utils.create_admin --email $(email) --password $(password) --name "$(name)"

seed:
	docker compose exec api python -m app.db.seed

reset-dev:
	docker compose down -v
	docker compose up -d --build
	@echo "Waiting for DB to start..."
	sleep 5
	docker compose exec api alembic upgrade head
	docker compose exec api python -m app.db.seed
