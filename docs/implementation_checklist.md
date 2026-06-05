# Implementation Checklist

This file maps `market_making_blueprint.md` to the implemented project artifacts.

## Boundary and Assumptions

- Maker-only, one bid and one ask maximum: `src/market_maker/strategy.py`, `src/market_maker/simulator.py`
- Linear ETH perpetual accounting in ETH/USD: `src/market_maker/accounting.py`
- Zero maker-fee baseline with configurable fee bps: `config/default.yaml`
- 250 ms baseline latency: `config/default.yaml`, `src/market_maker/simulator.py`
- Conservative queue-ahead official fill model: `config/default.yaml`, `src/market_maker/fill_model.py`
- Funding as continuous accrual over an 8-hour period: `src/market_maker/accounting.py`

## Data Audit

- Schema validation: `src/market_maker/data_loader.py`, `src/market_maker/data_audit.py`
- Timestamp ordering, nulls, duplicates: `src/market_maker/data_audit.py`
- Book monotonicity, crossed/locked books, spread/depth stats: `src/market_maker/data_audit.py`
- Trade/book alignment and funding gap checks: `src/market_maker/data_audit.py`
- Tick-size inference: `src/market_maker/data_audit.py`
- Audit output: `reports/baseline/audit_summary.csv`

## Strategy and Simulator

- Fair price with mid, microprice, and past-only trade imbalance: `src/market_maker/strategy.py`
- Funding target inventory: `src/market_maker/strategy.py`
- Inventory-skewed reservation price: `src/market_maker/strategy.py`
- Adaptive spread, volatility buffer, pressure side-stop, cooldown: `src/market_maker/strategy.py`, `src/market_maker/features.py`
- Inventory-aware size clipping and reduce-only EOD behavior: `src/market_maker/risk.py`, `src/market_maker/strategy.py`
- Same-timestamp priority that prevents new quotes from filling immediately: `src/market_maker/simulator.py`, `tests/test_event_ordering.py`
- Conservative and simple fill models: `src/market_maker/fill_model.py`

## Accounting and Metrics

- Cash, inventory, average cost, realized/unrealized PnL: `src/market_maker/accounting.py`
- Fees and funding PnL: `src/market_maker/accounting.py`
- Equity, liquidation-adjusted equity: `src/market_maker/accounting.py`, `src/market_maker/simulator.py`
- Total/daily PnL, fill statistics, inventory statistics, drawdown, Sharpe-like metric: `src/market_maker/metrics.py`
- Realized spread and adverse selection after fills: `src/market_maker/metrics.py`
- CSVs, plots, final report: `src/market_maker/reporting.py`, `reports/baseline/`

## Tests

- PnL accounting, fees, funding, mark-to-market: `tests/test_accounting.py`
- Simple and queue fill behavior: `tests/test_fill_model.py`
- Event ordering/no same-timestamp fill: `tests/test_event_ordering.py`
- Inventory clipping, no-lookahead feature state, daily aggregation, bad data: `tests/test_risk_strategy_metrics.py`

## Verified Commands

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/pytest
.venv/bin/mm-backtest audit --output-dir reports/audit_check
.venv/bin/mm-backtest run --output-dir reports/baseline
.venv/bin/mm-backtest run --fill-model simple --output-dir reports/simple_fill
```

The temporary `reports/audit_check` directory was removed after the verification pass; the committed report artifacts are `reports/baseline`, `reports/simple_fill`, and `reports/fill_model_comparison.*`.
