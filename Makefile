.PHONY: smoke reproduce robustness test

smoke:
	python3 scripts/reproduce.py --mode smoke

reproduce:
	python3 scripts/reproduce.py --mode standard

robustness:
	python3 scripts/run_robustness.py --mode standard

test:
	python3 -m pytest -q
