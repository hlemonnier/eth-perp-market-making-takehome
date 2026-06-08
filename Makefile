.PHONY: smoke reproduce robustness test
PYTHON ?= .venv/bin/python

smoke:
	$(PYTHON) scripts/reproduce.py --mode smoke

reproduce:
	$(PYTHON) scripts/reproduce.py --mode core

robustness:
	$(PYTHON) scripts/run_robustness.py --mode core

test:
	$(PYTHON) -m pytest -q
