# ETH Perpetual Market-Making Backtest

## Headline

This is a simulator-validation baseline, not evidence of a proven profitable market-making strategy. Conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.

## Assumptions

- Strategy is maker-only and keeps at most one bid and one ask live.
- Fill model: `conservative_queue`.
- Maker fee assumption: `0.5` bps.
- Latency assumption: `250` ms.
- Funding accrual uses latest known funding over `8.0` hour periods; positive funding is assumed to mean longs pay shorts.
- Inferred tick size: `0.1`.
- Cancel latency assumption: `250` ms.
- Queue depletion fraction: `0.0`.
- Forced-flat slippage: `0.5` bps.
- Forced-flat closing fee: `0.5` bps.
- Equal-timestamp policy: `trade_before_book` by default; reproduction outputs include an alternate `book_before_trade` policy check.
- End inventory is reported three ways: mid-marked total PnL, bid/ask liquidation-adjusted PnL, and forced-flat PnL after configured slippage and closing fee.
- Report provenance: `regenerated-2026-06-08`.

## Audit Summary

- Audit passed: `True`.
- Warning checks: `trades_duplicate_timestamps, one_tick_spread_share, mid_jump_outliers, trade_book_same_timestamp_share, trade_book_alignment, trade_book_alignment_age_ms`.

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
| trades_duplicate_timestamps | warn | 21530 | duplicate timestamps; pct=30.5148 |
| fundings_timestamp_order | ok | 0 | negative timestamp diffs |
| fundings_missing_values | ok | 0 | null cells |
| fundings_duplicate_rows | ok | 0 | targeted duplicate rows excluding loader metadata |
| fundings_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| orderbook_bid_monotonicity | ok | 0 | rows with increasing bid levels |
| orderbook_ask_monotonicity | ok | 0 | rows with decreasing ask levels |
| orderbook_negative_quantities | ok | 0 | rows with negative qty |
| orderbook_locked_or_crossed | ok | 0 | rows with bid >= ask |
| tick_inference | ok | 0.1 | modal positive price increment |
| spread_distribution | ok | 0.1 | stats={'tick_size': 0.1, 'spread_min': 0.09999999999990905, 'spread_p05': 0.09999999999990905, 'spread_p50': 0.09999999999990905, 'spread_p95': 0.1000000000003638, 'spread_p99': 0.1000000000003638, 'spread_max': 2.700000000000273, 'spread_ticks_p50': 0.9999999999990905, 'one_tick_or_less_pct': 80.49914883862611} |
| one_tick_spread_share | warn | 80.4991 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| mid_jump_outliers | warn | 48 | mid jump ticks p99=2.0000, max=48.0000 |
| depth_distribution | ok | 33.402 | stats={'bid_depth_1_p50': 33.402, 'ask_depth_1_p50': 32.717, 'bid_depth_5_p50': 147.01999999999998, 'ask_depth_5_p50': 150.068, 'bid_depth_10_p50': 257.80499999999995, 'ask_depth_10_p50': 282.256, 'bid_depth_20_p50': 721.3970000000002, 'ask_depth_20_p50': 704.3689999999999} |
| trade_price_size_finite | ok | 0 | non-finite trade price or size |
| trade_side_values | ok | 0 | is_maker_ask values outside {0,1} |
| trade_positive_size | ok | 0 | trade rows with size <= 0 |
| trade_book_same_timestamp_share | warn | 13.9634 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |
| trade_book_alignment | warn | 579 | trades not near matching side of BBO |
| trade_price_outside_visible_l2 | ok | 0 | trades outside visible L2 price range after backward book alignment |
| trade_book_alignment_age_ms | warn | 33439.9 | backward book alignment age stats={'p50_ms': 27.204994, 'p95_ms': 87.6368175, 'max_ms': 33439.860910999996} |
| funding_rate_finite | ok | 0 | non-finite funding rates |
| funding_rate_outliers | ok | 0.000539783 | absolute funding p99=0.00023601, max=0.00053978 |
| funding_gaps | ok | 40 | gaps over threshold=0 |
| day_boundary_2026-03-19 | ok | 0 | rows outside source date |
| day_boundary_2026-03-20 | ok | 0 | rows outside source date |
| day_boundary_2026-03-21 | ok | 0 | rows outside source date |

### Audit Warning/Error Details

| check | severity | value | detail |
| --- | --- | --- | --- |
| trades_duplicate_timestamps | warn | 21530 | duplicate timestamps; pct=30.5148 |
| one_tick_spread_share | warn | 80.4991 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| mid_jump_outliers | warn | 48 | mid jump ticks p99=2.0000, max=48.0000 |
| trade_book_same_timestamp_share | warn | 13.9634 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |
| trade_book_alignment | warn | 579 | trades not near matching side of BBO |
| trade_book_alignment_age_ms | warn | 33439.9 | backward book alignment age stats={'p50_ms': 27.204994, 'p95_ms': 87.6368175, 'max_ms': 33439.860910999996} |

### Event Ordering Exposure

The default simulator policy processes trades before book updates when timestamps are exactly equal. Audit output quantifies exposure to the alternate book-before-trade convention; reproduce workflows also write `event_ordering_sensitivity.csv` with actual default-vs-alternate backtests.

| book_rows | trade_rows | trades_with_same_timestamp_book | trades_with_same_timestamp_book_pct | book_updates_with_same_timestamp_trade | book_updates_with_same_timestamp_trade_pct | default_equal_timestamp_policy | sensitivity_policy_to_review |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3581577 | 70556 | 9852 | 13.9634 | 8846 | 0.246986 | trade_before_book | book_before_trade |

### Spread Statistics

| tick_size | spread_min | spread_p05 | spread_p50 | spread_p95 | spread_p99 | spread_max | spread_ticks_p50 | one_tick_or_less_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 2.7 | 1 | 80.4991 |

### Depth Statistics

| bid_depth_1_p50 | ask_depth_1_p50 | bid_depth_5_p50 | ask_depth_5_p50 | bid_depth_10_p50 | ask_depth_10_p50 | bid_depth_20_p50 | ask_depth_20_p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 33.402 | 32.717 | 147.02 | 150.068 | 257.805 | 282.256 | 721.397 | 704.369 |

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, fee-aware expected-edge gates, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior. Pressure and expected-edge stops are enforced at simulator level on existing live orders; fills during cancel latency are explicitly flagged.

## Results

- `total_pnl`: `13.175915373903983`
- `realized_trading_pnl`: `10.644974518457538`
- `unrealized_trading_pnl`: `2.6107889812081213`
- `realized_roundtrip_pnl`: `10.644974518457538`
- `inventory_mtm_pnl`: `2.6107889812081213`
- `funding_pnl`: `-0.028620796103210378`
- `fees`: `0.0512273296584266`
- `liquidation_adjusted_pnl`: `13.173689637347103`
- `forced_flat_pnl`: `13.164409419347235`
- `liquidation_cost`: `0.00222573655688052`
- `final_liquidation_cost`: `0.00222573655688052`
- `forced_flat_cost`: `0.011505954556747966`
- `total_fills`: `5.0`
- `fill_volume_eth`: `0.47648936062129577`
- `turnover_usd`: `1024.546593168532`
- `max_inventory`: `0.1280332675994882`
- `min_inventory`: `-0.08795404714246322`
- `mean_abs_inventory`: `0.04975980534955162`
- `max_drawdown`: `4.328587924394561`
- `sampled_1m_max_drawdown`: `4.1524990905008625`
- `sharpe_like_1m`: `1.2201889526773426`
- `pnl_per_turnover`: `0.012860240287516747`
- `pnl_per_eth`: `27.652066263817247`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | 10.2454 | 10.2454 | 9.34072 | 0.956811 | -0.028252 | 0.0238677 | 9.34072 | 0.956811 | -0.028252 | 0.0238677 | 1 | 1 | 0.133193 | 0.087954 | -0.0173824 | 0.087954 | 4.32859 | 4.1525 |
| 2026-03-20 | 10.2454 | 10.3763 | 0.130851 | 1.30425 | -1.12819 | -0.0178516 | 0.0273596 | 10.645 | -0.171382 | -0.0461036 | 0.0512273 | 1 | 2 | 0.082794 | 0.172548 | -0.0194561 | 0.128033 | 2.51037 | 2.2877 |
| 2026-03-21 | 10.3763 | 13.1759 | 2.79965 | 0 | 2.78217 | 0.0174828 | 0 | 10.645 | 2.61079 | -0.0286208 | 0.0512273 | 0 | 0 | 0 | 0 | -0.0445147 | 0.0445147 | 1.05321 | 1.00879 |

## Round-Trip And Holding-Time Diagnostics

Rows pair fills greedily when inventory is reduced by an opposite-side fill. Long holding periods indicate inventory-path PnL rather than clean high-frequency spread economics.

| entry_time | exit_time | entry_side | exit_side | quantity | entry_price | exit_price | holding_seconds | roundtrip_pnl | exit_order_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 03:34:20.946980007+00:00 | 2026-03-19 13:38:36.799916218+00:00 | ask | bid | 0.087954 | 2222.5 | 2116.3 | 36255.9 | 9.34072 | pending_cancel |
| 2026-03-19 13:38:36.799916218+00:00 | 2026-03-20 05:42:46.571920130+00:00 | bid | ask | 0.0452393 | 2116.3 | 2143.3 | 57849.8 | 1.22146 | live |
| 2026-03-20 04:38:01.884669239+00:00 | 2026-03-20 05:42:46.571920130+00:00 | bid | ask | 0.0455754 | 2142.3 | 2143.3 | 3884.69 | 0.0455754 | live |
| 2026-03-20 04:38:01.884669239+00:00 | 2026-03-20 05:42:48.679674362+00:00 | bid | ask | 0.0372185 | 2142.3 | 2143.3 | 3886.8 | 0.0372185 | live |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid | pressure_stop_violation_fills | pending_cancel_fills | pending_cancel_pressure_fills | live_fills | live_avg_realized_spread_5s | pending_cancel_avg_realized_spread_5s | average_quote_age_ms | average_book_age_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 0.476489 | 2 | 3 | 0.0952979 | 0.087954 | 204.909 | 0 | 0 | 1 | 0 | 4 | 0.1 | -2.3 | 2806.22 | 82.8248 |

### Fill Diagnostic Breakdowns

| breakdown | bucket | fills | avg_realized_spread_5s | avg_markout_1s | avg_quote_age_ms |
| --- | --- | --- | --- | --- | --- |
| side | ask | 3 | 0.116667 | 0.0666667 | 1999.94 |
| side | bid | 2 | -1.125 | -0.475 | 4015.64 |
| pressure_bucket | (-0.25, 0.25] | 2 | 0.1 | 0.1 | 2550.42 |
| pressure_bucket | (-0.75, -0.5] | 1 | 0.15 | 0 | 898.97 |
| pressure_bucket | (0.25, 0.5] | 1 | 0.05 | -0.4 | 5976.99 |
| pressure_bucket | (0.5, 0.75] | 1 | -2.3 | -0.55 | 2054.3 |
| quote_age_bucket_ms | 1000-5000 | 3 | -0.7 | -0.116667 | 2385.04 |
| quote_age_bucket_ms | 250-1000 | 1 | 0.15 | 0 | 898.97 |
| quote_age_bucket_ms | 5000-30000 | 1 | 0.05 | -0.4 | 5976.99 |
| queue_ahead_bucket | 20+ | 5 | -0.38 | -0.15 | 2806.22 |
| inventory_bucket | flat | 3 | 0.0833333 | -0.0666667 | 3692.61 |
| inventory_bucket | long_small | 1 | 0.15 | 0 | 898.97 |
| inventory_bucket | short_small | 1 | -2.3 | -0.55 | 2054.3 |
| spread_bucket | 0.1-0.5 | 2 | -1.125 | -0.475 | 4015.64 |
| spread_bucket | <=0.1 | 3 | 0.116667 | 0.0666667 | 1999.94 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 110017 | 5 | 110011 | 2345 | 4.54475e-05 | 4.54475e-05 | 0.999945 | refresh_reprice | 38271 | 2.38056 | 10.25 | 10.25 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| refresh_reprice | 38271 | 0 |
| pressure_stop_ask | 26180 | 0 |
| pressure_stop_bid | 22681 | 0 |
| expected_edge_bid | 9559 | 0 |
| quote_age_expired | 7050 | 0 |
| expected_edge_ask | 5673 | 0 |
| stale_book | 477 | 0 |
| expected_edge_jump_cooldown | 64 | 0 |
| quote_crossed_after_book_update | 47 | 0 |
| refresh_no_desired_quote | 7 | 0 |
| eod_reduce_only | 2 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.0271218 | 0.0497598 | 0.0466822 | -0.087954 | 0.128033 | 22.3097 | 72.7146 | 4.9757 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms | max_allowed_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 3581577 | -0.23 | 0.23 | 9.97347 | 51.9933 | 1000 |
| 5 | event_level_book | 3581577 | -0.38 | 0.38 | 36.488 | 75.1055 | 1000 |
| 30 | event_level_book | 3581577 | -0.45 | 0.45 | 59.4785 | 93.9174 | 1000 |

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -0.0512273 | 13.2784 | 10.6962 | 4.32859 | 5 | 1024.55 | 0.0129602 |
| 0 | 0 | 13.2271 | 10.645 | 4.32859 | 5 | 1024.55 | 0.0129102 |
| 0.5 | 0.0512273 | 13.1759 | 10.5937 | 4.32859 | 5 | 1024.55 | 0.0128602 |
| 1 | 0.102455 | 13.1247 | 10.5425 | 4.32859 | 5 | 1024.55 | 0.0128102 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection and inventory-directional risk; positive simple-fill PnL is not alpha evidence when it comes from carrying directional inventory.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.
- The included dataset covers only three days, so fill counts, drawdown, and PnL are not statistically reliable strategy-performance estimates.

## Conclusion

The run finished with mid-marked total PnL `13.1759` USD, forced-flat PnL `13.1644` USD, realized trading PnL `10.6450` USD, unrealized trading PnL `2.6108` USD, and funding PnL `-0.0286` USD. The strategy generated `5` fills and max drawdown `4.3286` USD under the selected fill model. Fill count is sparse and too small to support a statistically meaningful performance claim. Realized round-trip PnL is positive, but short-horizon realized-spread markouts are negative; do not interpret this as clean spread capture. `1` fills occurred while cancellation was pending, so cancel-latency adverse selection remains a key diagnostic.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `round_trips.csv`, `fee_sensitivity.csv`, `event_ordering_exposure.csv`
- Reproduction suite roots also include `fill_model_comparison.csv`, `event_ordering_sensitivity.csv`, and `run_scope.csv`.
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive round-trip PnL with negative short-horizon realized spreads should be read as inventory-path PnL, not clean spread economics. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
