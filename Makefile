PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install lint typecheck test demo

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install -e '.[dev]'

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

typecheck:
	$(BIN)/mypy --strict

test:
	$(BIN)/pytest --cov=agent_eval --cov-report=term-missing --cov-report=xml

demo:
	$(BIN)/agent-eval run examples/mock-demo.yaml
