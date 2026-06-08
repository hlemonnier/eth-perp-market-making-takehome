# ETH Perpetual Market-Making Backtest

## Headline

This is a simulator-validation baseline, not evidence of a proven profitable market-making strategy. Conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.

## Assumptions

- Strategy is maker-only and keeps at most one bid and one ask live.
- Fill model: `simple`.
- Maker fee assumption: `0.5` bps.
- Latency assumption: `250` ms.
- Funding accrual uses latest known funding over `8.0` hour periods; positive funding is assumed to mean longs pay shorts.
- Inferred tick size: `0.1`.
- Cancel latency assumption: `250` ms.
- Queue depletion fraction: `0.0`.
- Forced-flat slippage: `0.5` bps.
- End inventory is reported three ways: mid-marked total PnL, bid/ask liquidation-adjusted PnL, and forced-flat PnL after configured slippage.
- Git commit: `da54271-dirty`.

## Audit Summary

- Audit passed: `True`.
- Warning checks: `trades_duplicate_timestamps, one_tick_spread_share, trade_book_same_timestamp_share, trade_book_alignment`.

### Audit Check Details

| check | severity | value | detail |
| --- | --- | --- | --- |
| orderbook_schema | ok | 0 | missing=[] |
| trades_schema | ok | 0 | missing=[] |
| fundings_schema | ok | 0 | missing=[] |
| orderbook_timestamp_order | ok | 0 | negative timestamp diffs |
| orderbook_missing_values | ok | 0 | null cells |
| orderbook_duplicate_rows | ok | 0 | targeted duplicate rows excluding loader metadata |
| orderbook_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| trades_timestamp_order | ok | 0 | negative timestamp diffs |
| trades_missing_values | ok | 0 | null cells |
| trades_duplicate_rows | ok | 0 | targeted duplicate rows excluding loader metadata |
| trades_duplicate_timestamps | warn | 324 | duplicate timestamps; pct=34.0336 |
| fundings_timestamp_order | ok | 0 | negative timestamp diffs |
| fundings_missing_values | ok | 0 | null cells |
| fundings_duplicate_rows | ok | 0 | targeted duplicate rows excluding loader metadata |
| fundings_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| orderbook_bid_monotonicity | ok | 0 | rows with increasing bid levels |
| orderbook_ask_monotonicity | ok | 0 | rows with decreasing ask levels |
| orderbook_negative_quantities | ok | 0 | rows with negative qty |
| orderbook_locked_or_crossed | ok | 0 | rows with bid >= ask |
| tick_inference | ok | 0.1 | modal positive price increment |
| spread_distribution | ok | 0.1 | stats={'tick_size': 0.1, 'spread_min': 0.09999999999990905, 'spread_p05': 0.09999999999990905, 'spread_p50': 0.09999999999990905, 'spread_p95': 0.1000000000003638, 'spread_p99': 0.1000000000003638, 'spread_max': 1.199999999999818, 'spread_ticks_p50': 0.9999999999990905, 'one_tick_or_less_pct': 79.254} |
| one_tick_spread_share | warn | 79.254 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| mid_jump_outliers | ok | 10.5 | mid jump ticks p99=1.0000, max=10.5000 |
| depth_distribution | ok | 34.268 | stats={'bid_depth_1_p50': 34.268, 'ask_depth_1_p50': 34.4695, 'bid_depth_5_p50': 138.35399999999998, 'ask_depth_5_p50': 166.225, 'bid_depth_10_p50': 224.545, 'ask_depth_10_p50': 284.77200000000005, 'bid_depth_20_p50': 677.1329999999999, 'ask_depth_20_p50': 726.169} |
| trade_price_size_finite | ok | 0 | non-finite trade price or size |
| trade_side_values | ok | 0 | is_maker_ask values outside {0,1} |
| trade_positive_size | ok | 0 | trade rows with size <= 0 |
| trade_book_same_timestamp_share | warn | 11.7647 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |
| trade_book_alignment | warn | 4 | trades not near matching side of BBO |
| trade_price_outside_visible_l2 | ok | 0 | trades outside visible L2 price range after backward book alignment |
| trade_book_alignment_age_ms | ok | 217.736 | backward book alignment age stats={'p50_ms': 25.556966, 'p95_ms': 60.67842289999998, 'max_ms': 217.735871} |
| funding_rate_finite | ok | 0 | non-finite funding rates |
| funding_rate_outliers | ok | 0.000137808 | absolute funding p99=0.00012006, max=0.00013781 |
| funding_gaps | ok | 21 | gaps over threshold=0 |
| day_boundary_2026-03-19 | ok | 0 | rows outside source date |

### Audit Warning/Error Details

| check | severity | value | detail |
| --- | --- | --- | --- |
| trades_duplicate_timestamps | warn | 324 | duplicate timestamps; pct=34.0336 |
| one_tick_spread_share | warn | 79.254 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| trade_book_same_timestamp_share | warn | 11.7647 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |
| trade_book_alignment | warn | 4 | trades not near matching side of BBO |

### Event Ordering Sensitivity

The simulator processes trades before book updates when timestamps are exactly equal. This table quantifies how much data is exposed to the alternate book-before-trade convention.

| book_rows | trade_rows | trades_with_same_timestamp_book | trades_with_same_timestamp_book_pct | book_updates_with_same_timestamp_trade | book_updates_with_same_timestamp_trade_pct | default_equal_timestamp_policy | sensitivity_policy_to_review |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 50000 | 952 | 112 | 11.7647 | 103 | 0.206 | trade_before_book | book_before_trade |

### Spread Statistics

| tick_size | spread_min | spread_p05 | spread_p50 | spread_p95 | spread_p99 | spread_max | spread_ticks_p50 | one_tick_or_less_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 1.2 | 1 | 79.254 |

### Depth Statistics

| bid_depth_1_p50 | ask_depth_1_p50 | bid_depth_5_p50 | ask_depth_5_p50 | bid_depth_10_p50 | ask_depth_10_p50 | bid_depth_20_p50 | ask_depth_20_p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 34.268 | 34.4695 | 138.354 | 166.225 | 224.545 | 284.772 | 677.133 | 726.169 |

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, fee-aware expected-edge gates, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior. Pressure and expected-edge stops are enforced at simulator level on existing live orders; fills during cancel latency are explicitly flagged.

## Results

- `total_pnl`: `-1.8579935053883425`
- `realized_trading_pnl`: `0.0`
- `unrealized_trading_pnl`: `-1.839337818685721`
- `realized_roundtrip_pnl`: `0.0`
- `inventory_mtm_pnl`: `-1.839337818685721`
- `funding_pnl`: `-0.0016232375120536348`
- `fees`: `0.017032449190596592`
- `liquidation_adjusted_pnl`: `-1.8657251784673783`
- `forced_flat_pnl`: `-1.8826652741833734`
- `liquidation_cost`: `0.007731673079035772`
- `final_liquidation_cost`: `0.007731673079035772`
- `forced_flat_cost`: `0.024671768795030857`
- `total_fills`: `2.0`
- `fill_volume_eth`: `0.1546334615792639`
- `turnover_usd`: `340.6489838119319`
- `max_inventory`: `0.1546334615792639`
- `min_inventory`: `0.0`
- `mean_abs_inventory`: `0.13080159546461423`
- `max_drawdown`: `2.1191292590680404`
- `sampled_1m_max_drawdown`: `1.9335576438538549`
- `sharpe_like_1m`: `-5.382646864500572`
- `pnl_per_turnover`: `-0.005454275790278353`
- `pnl_per_eth`: `-12.01546862116871`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -1.85799 | -1.85799 | 0 | -1.83934 | -0.00162324 | 0.0170324 | 0 | -1.83934 | -0.00162324 | 0.0170324 | 2 | 0 | 0.154633 | 0 | 0.130802 | 0.154633 | 2.11913 | 1.93356 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid | pressure_stop_violation_fills | pending_cancel_fills | pending_cancel_pressure_fills | live_fills | live_avg_realized_spread_5s | pending_cancel_avg_realized_spread_5s | average_quote_age_ms | average_book_age_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 0.154633 | 2 | 0 | 0.0773167 | 0.0773167 | 170.324 | 0.2 | 0 | 2 | 1 | 0 | 0 | -1.4 | 1755.82 | 43.824 |

### Fill Diagnostic Breakdowns

| breakdown | bucket | fills | avg_realized_spread_5s | avg_markout_1s | avg_quote_age_ms |
| --- | --- | --- | --- | --- | --- |
| side | bid | 2 | -1.4 | -0.7 | 1755.82 |
| pressure_bucket | (-1.011, -0.75] | 1 | -0.85 | -1.4 | 1167.99 |
| pressure_bucket | (0.25, 0.5] | 1 | -1.95 | 0 | 2343.66 |
| quote_age_bucket_ms | 1000-5000 | 2 | -1.4 | -0.7 | 1755.82 |
| queue_ahead_bucket | 20+ | 2 | -1.4 | -0.7 | 1755.82 |
| inventory_bucket | flat | 1 | -1.95 | 0 | 2343.66 |
| inventory_bucket | long_small | 1 | -0.85 | -1.4 | 1167.99 |
| spread_bucket | <=0.1 | 2 | -1.4 | -0.7 | 1755.82 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1187 | 2 | 1184 | 20 | 0.00168492 | 0.00168492 | 0.997473 | refresh_reprice | 409 | 2.4111 | 8.94124 | 10.25 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| refresh_reprice | 409 | 0 |
| pressure_stop_bid | 354 | 0 |
| expected_edge_ask | 213 | 0 |
| pressure_stop_ask | 164 | 0 |
| quote_age_expired | 41 | 0 |
| expected_edge_bid | 3 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.130802 | 0.130802 | 0.0511367 | 0 | 0.154633 | 88.8889 | 0 | 11.1111 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 50000 | -0.5 | 0.7 | 35.046 | 41.0643 |
| 5 | event_level_book | 50000 | -1.4 | 1.6 | 17.5705 | 28.7314 |
| 30 | event_level_book | 50000 | -1.95 | 2.15 | 44.4963 | 58.4632 |

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -0.0170324 | -1.82393 | 0.0170324 | 2.11913 | 2 | 340.649 | -0.00535428 |
| 0 | 0 | -1.84096 | 0 | 2.11913 | 2 | 340.649 | -0.00540428 |
| 0.5 | 0.0170324 | -1.85799 | -0.0170324 | 2.11913 | 2 | 340.649 | -0.00545428 |
| 1 | 0.0340649 | -1.87503 | -0.0340649 | 2.11913 | 2 | 340.649 | -0.00550428 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection; it is not a better-performance upper bound.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.

## Conclusion

The run finished with mid-marked total PnL `-1.8580` USD, forced-flat PnL `-1.8827` USD, realized trading PnL `0.0000` USD, unrealized trading PnL `-1.8393` USD, and funding PnL `-0.0016` USD. The strategy generated `2` fills and max drawdown `2.1191` USD under the selected fill model. Most reported PnL is mark-to-market inventory PnL rather than realized spread capture, so the result should be treated as a conservative simulator validation, not proof of robust market-making edge.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`, `event_ordering_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive forced-flat PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
