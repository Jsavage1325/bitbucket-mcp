.PHONY: install lint format test integration-test smoke test-all build run

install:
	uv sync

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests

test:
	uv run pytest tests/unit -q

integration-test:
	uv run pytest tests/integration -q

smoke:
	uv run pytest tests/smoke -q

test-all:
	uv run pytest tests/ -q

build:
	uv build

run:
	uv run bitbucket-mcp-server
