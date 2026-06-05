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

- `total_pnl`: `-10.174922570107897`
- `realized_trading_pnl`: `-9.826689015333898`
- `unrealized_trading_pnl`: `-0.6235789001586057`
- `funding_pnl`: `0.2753453453846977`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `-10.175392486385332`
- `total_fills`: `85.0`
- `fill_volume_eth`: `8.540931780727295`
- `turnover_usd`: `18354.530691167045`
- `max_inventory`: `0.5112305730310635`
- `min_inventory`: `-0.4714267073195671`
- `mean_abs_inventory`: `0.14701059558288349`
- `max_drawdown`: `22.43805100709705`
- `sharpe_like_1m`: `-0.26311711617660705`
- `pnl_per_turnover`: `-0.0005543548206876512`
- `pnl_per_eth`: `-1.1913129423498874`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | realized_trading_pnl | unrealized_trading_pnl | funding_pnl | fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -12.6542 | -12.6542 | -14.2351 | 1.5072 | 0.0736893 | 0 | 16 | 19 | 1.60024 | 1.90017 | 0.022694 | 0.461692 | 22.4381 |
| 2026-03-20 | -12.6542 | -7.67751 | 4.97667 | -8.23512 | 0.379986 | 0.177621 | 0 | 17 | 16 | 1.62381 | 1.63948 | 0.0860344 | 0.511231 | 11.7279 |
| 2026-03-21 | -7.67751 | -10.1749 | -2.49741 | -9.82669 | -0.623579 | 0.275345 | 0 | 10 | 7 | 1.05112 | 0.726119 | -0.0751431 | 0.471427 | 5.62936 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 85 | 8.54093 | 43 | 42 | 0.100482 | 0.101314 | 215.936 | 0.261176 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0111751 | 0.147011 | 0.190764 | -0.471427 | 0.511231 | 57.5793 | 42.143 | 0.277713 |

## Realized Spread and Adverse Selection

| horizon_seconds | average_realized_spread | average_toxicity |
| --- | --- | --- |
| 1 | -0.413529 | 0.674706 |
| 5 | -0.413529 | 0.674706 |
| 30 | -0.231176 | 0.492353 |

## Conclusion

The run finished with total PnL `-10.1749` USD, realized trading PnL `-9.8267` USD, unrealized trading PnL `-0.6236` USD, and funding PnL `0.2753` USD. The strategy generated `85` fills and max drawdown `22.4381` USD under the selected fill model. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `inventory_stats.csv`, `realized_spread.csv`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory.
