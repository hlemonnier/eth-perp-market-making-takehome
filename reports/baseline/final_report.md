# ETH Perpetual Market-Making Backtest

## Assumptions

- Strategy is maker-only and keeps at most one bid and one ask live.
- Official result uses the conservative queue-ahead fill model.
- Maker fee assumption: `0.0` bps.
- Latency assumption: `250` ms.
- Funding accrual uses latest known funding over `8.0` hour periods.
- Inferred tick size: `0.1`.
- End inventory is marked to mid for baseline PnL and to bid/ask for liquidation-adjusted sensitivity.

## Audit Summary

- Audit passed: `True`.
- Warning checks: `trades_duplicate_timestamps, trade_book_alignment`.

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior.

## Results

- `total_pnl`: `12.820005118218887`
- `realized_trading_pnl`: `0.05482988557264362`
- `unrealized_trading_pnl`: `12.66291480579653`
- `funding_pnl`: `0.10226042684985265`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `12.811302662716628`
- `total_fills`: `6.0`
- `fill_volume_eth`: `0.5394893546210648`
- `turnover_usd`: `1160.5083924108621`
- `max_inventory`: `0.08731790991119401`
- `min_inventory`: `-0.1740491100442491`
- `mean_abs_inventory`: `0.06492235637242422`
- `max_drawdown`: `4.824186210310908`
- `sharpe_like_1m`: `0.8950028639474141`
- `pnl_per_turnover`: `0.011046887038521424`
- `pnl_per_eth`: `23.763221662128267`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | realized_trading_pnl | unrealized_trading_pnl | funding_pnl | fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 |
| 2026-03-20 | 0 | 0.546307 | 0.546307 | 0.471517 | 0.032761 | 0.0420293 | 0 | 1 | 2 | 0.0873179 | 0.130999 | 0.067307 | 0.0873179 | 4.82419 |
| 2026-03-21 | 0.546307 | 12.82 | 12.2737 | 0.0548299 | 12.6629 | 0.10226 | 0 | 1 | 2 | 0.0954022 | 0.22577 | -0.125355 | 0.174049 | 2.18271 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 0.539489 | 2 | 4 | 0.0899149 | 0.0913601 | 193.418 | 0.2 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.019374 | 0.0649224 | 0.0884807 | -0.174049 | 0.0873179 | 26.0819 | 34.1356 | 39.7825 |

## Realized Spread and Adverse Selection

| horizon_seconds | average_realized_spread | average_toxicity |
| --- | --- | --- |
| 1 | -0.15 | 0.35 |
| 5 | -0.15 | 0.35 |
| 30 | -0.0166667 | 0.216667 |

## Conclusion

The run finished with total PnL `12.8200` USD, realized trading PnL `0.0548` USD, unrealized trading PnL `12.6629` USD, and funding PnL `0.1023` USD. The strategy generated `6` fills and max drawdown `4.8242` USD under the selected fill model. Most reported PnL is mark-to-market inventory PnL rather than realized spread capture, so the result should be treated as a conservative simulator validation, not proof of robust market-making edge.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `inventory_stats.csv`, `realized_spread.csv`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory.
