.PHONY: up down reset test coverage train

up:            ## Start the platform (one command)
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	docker compose up --build -d

down:          ## Stop the platform (data volumes are kept)
	docker compose down

reset:         ## Stop the platform and erase all data
	docker compose down -v

test:          ## Tests (end-to-end tests are skipped when the platform is not running)
	uv run --no-sync pytest -q

coverage:      ## Tests with branch coverage of services/
	uv run --no-sync pytest -q --cov --cov-report=term-missing
