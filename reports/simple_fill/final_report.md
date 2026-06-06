# ETH Perpetual Market-Making Backtest

## Headline

This is a simulator-validation baseline, not evidence of a proven profitable market-making strategy. Conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.

## Assumptions

- Strategy is maker-only and keeps at most one bid and one ask live.
- Fill model: `simple`.
- Maker fee assumption: `0.0` bps.
- Latency assumption: `250` ms.
- Funding accrual uses latest known funding over `8.0` hour periods; positive funding is assumed to mean longs pay shorts.
- Inferred tick size: `0.1`.
- End inventory is marked to mid for baseline PnL and to bid/ask for liquidation-adjusted sensitivity.
- Git commit: `c5e7f4f`.

## Audit Summary

- Audit passed: `True`.
- Warning checks: `trades_duplicate_timestamps, one_tick_spread_share, mid_jump_outliers, trade_book_alignment, trade_book_alignment_age_ms`.

### Audit Check Details

| check | severity | value | detail |
| --- | --- | --- | --- |
| orderbook_schema | ok | 0 | missing=[] |
| trades_schema | ok | 0 | missing=[] |
| fundings_schema | ok | 0 | missing=[] |
| orderbook_timestamp_order | ok | 0 | negative timestamp diffs |
| orderbook_missing_values | ok | 0 | null cells |
| orderbook_duplicate_rows | ok | 0 | exact duplicate rows excluding loader metadata |
| orderbook_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| trades_timestamp_order | ok | 0 | negative timestamp diffs |
| trades_missing_values | ok | 0 | null cells |
| trades_duplicate_rows | ok | 0 | exact duplicate rows excluding loader metadata |
| trades_duplicate_timestamps | warn | 21530 | duplicate timestamps; pct=30.5148 |
| fundings_timestamp_order | ok | 0 | negative timestamp diffs |
| fundings_missing_values | ok | 0 | null cells |
| fundings_duplicate_rows | ok | 0 | exact duplicate rows excluding loader metadata |
| fundings_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| orderbook_bid_monotonicity | ok | 0 | rows with increasing bid levels |
| orderbook_ask_monotonicity | ok | 0 | rows with decreasing ask levels |
| orderbook_negative_quantities | ok | 0 | rows with negative qty |
| orderbook_locked_or_crossed | ok | 0 | rows with bid >= ask |
| tick_inference | ok | 0.1 | modal positive price increment |

_Showing 20 of 36 rows._

### Spread Statistics

| tick_size | spread_min | spread_p05 | spread_p50 | spread_p95 | spread_p99 | spread_max | spread_ticks_p50 | one_tick_or_less_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 2.7 | 1 | 80.4991 |

### Depth Statistics

| bid_depth_1_p50 | ask_depth_1_p50 | bid_depth_5_p50 | ask_depth_5_p50 | bid_depth_10_p50 | ask_depth_10_p50 | bid_depth_20_p50 | ask_depth_20_p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 33.402 | 32.717 | 147.02 | 150.068 | 257.805 | 282.256 | 721.397 | 704.369 |

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior.

## Results

- `total_pnl`: `-30.36097682278542`
- `realized_trading_pnl`: `-30.695593444272088`
- `unrealized_trading_pnl`: `0.0`
- `funding_pnl`: `0.3346166214854924`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `-30.36097682278542`
- `total_fills`: `894.0`
- `fill_volume_eth`: `80.70585558285516`
- `turnover_usd`: `173676.43427150417`
- `max_inventory`: `0.49487042616451543`
- `min_inventory`: `-0.4757443316385213`
- `mean_abs_inventory`: `0.15461624281739197`
- `max_drawdown`: `35.588139517511344`
- `sampled_1m_max_drawdown`: `35.42287936722122`
- `sharpe_like_1m`: `-0.798997035369635`
- `pnl_per_turnover`: `-0.00017481345094477724`
- `pnl_per_eth`: `-0.3761929862897729`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -8.60433 | -8.60433 | -8.6893 | 0 | 0.0849694 | 0 | -8.6893 | 0 | 0.0849694 | 0 | 184 | 187 | 17.1216 | 17.1216 | 0.063318 | 0.435385 | 22.3432 |
| 2026-03-20 | -8.60433 | -28.725 | -20.1206 | -20.3259 | 0.0707781 | 0.134528 | 0 | -29.0152 | 0.0707781 | 0.219498 | 0 | 170 | 178 | 15.4025 | 15.5566 | 0.116748 | 0.49487 | 24.6816 |
| 2026-03-21 | -28.725 | -30.361 | -1.63602 | -1.68036 | -0.0707781 | 0.115119 | 0 | -30.6956 | 0 | 0.334617 | 0 | 86 | 89 | 7.82884 | 7.67479 | -0.0876427 | 0.475744 | 5.23943 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 894 | 80.7059 | 440 | 454 | 0.090275 | 0.0980183 | 194.269 | 0.221868 |

## Order Statistics

| placed_orders | cancelled_orders | resized_orders | fill_to_order_ratio | average_quote_lifetime_seconds | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- |
| 111998 | 111288 | 8342 | 0.00798229 | 4.2974 | 18.8565 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0307803 | 0.154616 | 0.188228 | -0.475744 | 0.49487 | 54.4781 | 44.9896 | 0.532284 |

## Realized Spread and Adverse Selection

| horizon_seconds | average_realized_spread | average_toxicity |
| --- | --- | --- |
| 1 | -0.368904 | 0.590772 |
| 5 | -0.363311 | 0.585179 |
| 30 | -0.263311 | 0.485179 |

## Maker Fee Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_pnl_per_turnover |
| --- | --- | --- | --- |
| 0 | 0 | -30.361 | -0.000174813 |
| 1 | 17.3676 | -47.7286 | -0.000274813 |
| 2 | 34.7353 | -65.0963 | -0.000374813 |

## Conclusion

The run finished with total PnL `-30.3610` USD, realized trading PnL `-30.6956` USD, unrealized trading PnL `0.0000` USD, and funding PnL `0.3346` USD. The strategy generated `894` fills and max drawdown `35.5881` USD under the selected fill model. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
