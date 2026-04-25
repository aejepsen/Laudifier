.PHONY: test cov mutmut mutmut-results lint clean

VENV := ../.venv/bin

test:
	$(VENV)/python -m pytest -q tests/

cov:
	$(VENV)/python -m pytest tests/ \
		--cov=backend --cov-branch \
		--cov-report=term-missing:skip-covered \
		--cov-report=xml:coverage.xml \
		--cov-report=html:htmlcov \
		--cov-fail-under=80

mutmut:
	rm -rf mutants
	$(VENV)/python -m mutmut run --max-children=4

mutmut-results:
	$(VENV)/python -m mutmut results

clean:
	rm -rf mutants htmlcov coverage.xml .pytest_cache __pycache__
