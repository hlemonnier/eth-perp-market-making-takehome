# Full-Dataset Bot Backtest Evidence Index

This root report is an aggregate index for the full three-day market-making bot backtest artifacts under `reports/full/`. It is not a standalone profitability claim and should not be read as a duplicate of the conservative baseline report.

## Scope

- Dataset: ETH perpetual order book, trades, and funding rows for 2026-03-19 through 2026-03-21.
- Baseline report: `reports/full/baseline/final_report.md`.
- Simple-fill stress report: `reports/full/simple_fill/final_report.md`.
- Full-dataset robustness core: `reports/full/robustness_core/grid_results.csv`.
- Full-dataset ablation core: `reports/full/ablations_core.csv` and `reports/full/ablations_core/ablation_day_results.csv`.
- Fill-model comparison: `reports/full/fill_model_comparison.csv`.
- Event-ordering sensitivity: `reports/full/event_ordering_sensitivity.csv`.

## Main Reading

The conservative baseline ended positive on forced-flat PnL, but it had only 5 fills and negative short-horizon realized-spread markouts. That is too sparse to support a deployable market-making edge claim.

The simple-fill run is useful as an adverse-selection and inventory-risk stress. Its PnL is dominated by mark-to-market short inventory exposure, not clean spread capture.

The full robustness core is the central evidence table. Partial-queue, cancel-latency, and higher-fee variants expose that the strategy is fragile under more realistic assumptions.

The ablation core covers all three dataset days using independent day-level runs to avoid the full wide-order-book memory load. It is a component diagnostic, not a replacement for the continuous baseline backtest.

## Submission Framing

The defensible claim is:

> This project implements and backtests an event-driven ETH perpetual market-making bot with realistic order lifecycle, fees, cancel latency, queue assumptions, forced-flat accounting, and fill-level adverse-selection diagnostics. The implemented strategy is not proven live-deployable, but the submission satisfies the market-making bot/backtest scope and analyzes the strategy limits honestly.

Do not frame these artifacts as proof of a profitable live ETH perp market-making strategy.
