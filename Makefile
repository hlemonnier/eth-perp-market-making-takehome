.PHONY: smoke reproduce robustness full-robustness test setup
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then printf '%s\n' .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then printf '%s\n' python3; else printf '%s\n' python; fi)

smoke:
	$(PYTHON) scripts/reproduce.py --mode smoke

reproduce:
	$(PYTHON) scripts/reproduce.py --mode core --sample-rows 5000

robustness:
	$(PYTHON) scripts/run_robustness.py --mode core --sample-rows 5000

full-robustness:
	$(PYTHON) scripts/run_robustness.py --mode full_core --output-dir reports/full/robustness_core

test:
	$(PYTHON) -m pytest -q

setup:
	$(PYTHON) -m pip install -e ".[dev]"
