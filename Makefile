.PHONY: install test lint check

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests

check: test lint
