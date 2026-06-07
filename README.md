# ETH Perpetual Market-Making Take-Home

This repository contains the provided ETH perpetual take-home data and an event-driven market-making backtest implementation guided by [`market_making_blueprint.md`](market_making_blueprint.md).

## Assignment

Design a market-making bot and backtest it on three calendar days of historical data, `2026-03-19` through `2026-03-21`.

Expected output:

- Strategy description
- Backtesting simulator with fills, inventory tracking, and PnL calculation
- Performance metrics for the evaluation period
- Brief conclusions and analysis

## Data

Instrument: single ETH perpetual market around 2200 USD.

| Folder | Files | Contents |
| --- | --- | --- |
| `data/orderbook/` | one parquet per day | 20-level L2 snapshots: `datetime`, `bid_price_i`, `ask_price_i`, `bid_qty_i`, `ask_qty_i` |
| `data/trades/` | one parquet per day | `datetime`, `price`, `size`, `is_maker_ask`; `1` means buyer aggressor hit resting asks, `0` means seller aggressor hit resting bids |
| `data/fundings/` | one parquet per day | `datetime`, `funding_rate`, approximately every 20 seconds |

The large order book parquet files are tracked with Git LFS. After cloning, run:

```bash
git lfs pull
```

## Implementation

The code follows the blueprint module boundaries:

- `src/market_maker/data_loader.py`: parquet loading, schema validation, timestamp normalization
- `src/market_maker/data_audit.py`: data quality checks and tick-size inference
- `src/market_maker/events.py`: reference timestamp-group event helpers; the simulator uses a faster array loop with the same trade-before-quote ordering
- `src/market_maker/book_state.py`: BBO, mid, microprice, spread, depth, queue ahead
- `src/market_maker/features.py`: past-only rolling volatility and trade imbalance
- `src/market_maker/strategy.py`: maker-only inventory-skewed quoting logic
- `src/market_maker/fill_model.py`: simple and conservative queue-ahead fill models
- `src/market_maker/accounting.py`: cash, inventory, average cost, realized/unrealized PnL, fees, funding
- `src/market_maker/risk.py`: inventory clipping, kill switch, cooldown, reduce-only window
- `src/market_maker/simulator.py`: chronological event loop
- `src/market_maker/metrics.py`: total, daily, fill, order-lifecycle, inventory, drawdown, realized spread metrics
- `src/market_maker/reporting.py`: CSV outputs, plots, and Markdown report

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run

Audit only:

```bash
mm-backtest audit --output-dir reports/baseline
```

Audit plus baseline backtest:

```bash
mm-backtest run --output-dir reports/baseline
```

Backtests fail fast if the audit has error-severity checks. Use `--allow-audit-errors` only for deliberate diagnostics.

Run aggressive simple-fill sensitivity:

```bash
mm-backtest run --fill-model simple --output-dir reports/simple_fill
```

## Outputs

The runner writes:

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `final_report.md`
- plots under `plots/`

## Tests

```bash
pytest
```

The tests cover the toy examples from the blueprint plus the review-critical regressions: long/short PnL accounting, fees, funding, simple fills, conservative queue fills, same-timestamp stable loader ordering, same-timestamp no-fill ordering, cancellation timestamps, max quote age enforcement, immediate kill-switch cancellation, inventory clipping, reduce-only no-flip behavior, tick rounding, daily PnL decomposition, event-level realized-spread marks, report fill-model text, and audit validation/fail-fast behavior.
