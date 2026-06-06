# ETH Perpetual Market-Making Backtest

## Headline

This is a simulator-validation baseline, not evidence of a proven profitable market-making strategy. Conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.

## Assumptions

- Strategy is maker-only and keeps at most one bid and one ask live.
- Fill model: `conservative_queue`.
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

- `total_pnl`: `-6.6674395847255346`
- `realized_trading_pnl`: `-12.84754356836326`
- `unrealized_trading_pnl`: `5.936892987227409`
- `funding_pnl`: `0.2432109964102914`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `-6.671742937629879`
- `total_fills`: `27.0`
- `fill_volume_eth`: `2.8716861713918704`
- `turnover_usd`: `6199.084139322756`
- `max_inventory`: `0.25760985216055193`
- `min_inventory`: `-0.3401195269919246`
- `mean_abs_inventory`: `0.13389794406909408`
- `max_drawdown`: `22.048599612612904`
- `sampled_1m_max_drawdown`: `21.118349884461306`
- `sharpe_like_1m`: `-0.21292222843627984`
- `pnl_per_turnover`: `-0.001075552361425755`
- `pnl_per_eth`: `-2.321785594521949`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -11.8892 | -11.8892 | -12.8894 | 0.912057 | 0.0880968 | 0 | -12.8894 | 0.912057 | 0.0880968 | 0 | 6 | 6 | 0.612076 | 0.686019 | 0.126275 | 0.233874 | 21.1183 |
| 2026-03-20 | -11.8892 | -11.4414 | 0.447832 | 0.295841 | 0.0694654 | 0.0825257 | 0 | -12.5936 | 0.981522 | 0.170623 | 0 | 4 | 5 | 0.427621 | 0.588005 | 0.0653309 | 0.25761 | 6.8526 |
| 2026-03-21 | -11.4414 | -6.66744 | 4.77398 | -0.253982 | 4.95537 | 0.0725884 | 0 | -12.8475 | 5.93689 | 0.243211 | 0 | 3 | 3 | 0.353113 | 0.204853 | -0.13632 | 0.34012 | 3.54957 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | 2.87169 | 13 | 14 | 0.106359 | 0.108449 | 229.596 | 0.224074 |

## Order Statistics

| placed_orders | cancelled_orders | resized_orders | fill_to_order_ratio | average_quote_lifetime_seconds | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- |
| 112349 | 112322 | 8358 | 0.000240323 | 4.33705 | 18.56 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0183929 | 0.133898 | 0.154522 | -0.34012 | 0.25761 | 50.1273 | 49.6181 | 0.254571 |

## Realized Spread and Adverse Selection

| horizon_seconds | average_realized_spread | average_toxicity |
| --- | --- | --- |
| 1 | -0.664815 | 0.888889 |
| 5 | -0.664815 | 0.888889 |
| 30 | -0.568519 | 0.792593 |

## Maker Fee Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_pnl_per_turnover |
| --- | --- | --- | --- |
| 0 | 0 | -6.66744 | -0.00107555 |
| 1 | 0.619908 | -7.28735 | -0.00117555 |
| 2 | 1.23982 | -7.90726 | -0.00127555 |

## Conclusion

The run finished with total PnL `-6.6674` USD, realized trading PnL `-12.8475` USD, unrealized trading PnL `5.9369` USD, and funding PnL `0.2432` USD. The strategy generated `27` fills and max drawdown `22.0486` USD under the selected fill model. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
