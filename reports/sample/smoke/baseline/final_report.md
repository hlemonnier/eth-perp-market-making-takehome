# ETH Perpetual Market-Making Backtest

## Headline

This report backtests the implemented market-making bot over the selected dataset. It is not evidence of a proven live-profitable strategy: conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.

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
- Report provenance: `not embedded`.

## Audit Summary

- Audit passed: `True`.
- Warning checks: `trades_duplicate_timestamps, one_tick_spread_share, trade_book_same_timestamp_share`.

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
| trades_duplicate_timestamps | warn | 5 | duplicate timestamps; pct=29.4118 |
| fundings_timestamp_order | ok | 0 | negative timestamp diffs |
| fundings_missing_values | ok | 0 | null cells |
| fundings_duplicate_rows | ok | 0 | targeted duplicate rows excluding loader metadata |
| fundings_duplicate_timestamps | ok | 0 | duplicate timestamps; pct=0.0000 |
| orderbook_bid_monotonicity | ok | 0 | rows with increasing bid levels |
| orderbook_ask_monotonicity | ok | 0 | rows with decreasing ask levels |
| orderbook_negative_quantities | ok | 0 | rows with negative qty |
| orderbook_locked_or_crossed | ok | 0 | rows with bid >= ask |
| tick_inference | ok | 0.1 | modal positive price increment |
| spread_distribution | ok | 0.1 | stats={'tick_size': 0.1, 'spread_min': 0.09999999999990905, 'spread_p05': 0.09999999999990905, 'spread_p50': 0.09999999999990905, 'spread_p95': 0.1000000000003638, 'spread_p99': 0.1000000000003638, 'spread_max': 0.20000000000027285, 'spread_ticks_p50': 0.9999999999990905, 'one_tick_or_less_pct': 79.80000000000001} |
| one_tick_spread_share | warn | 79.8 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| mid_jump_outliers | ok | 5 | mid jump ticks p99=1.0000, max=5.0000 |
| depth_distribution | ok | 38.908 | stats={'bid_depth_1_p50': 38.908, 'ask_depth_1_p50': 35.227000000000004, 'bid_depth_5_p50': 130.12, 'ask_depth_5_p50': 161.73000000000002, 'bid_depth_10_p50': 220.59699999999998, 'ask_depth_10_p50': 253.698, 'bid_depth_20_p50': 641.835, 'ask_depth_20_p50': 756.0095} |
| trade_price_size_finite | ok | 0 | non-finite trade price or size |
| trade_side_values | ok | 0 | is_maker_ask values outside {0,1} |
| trade_positive_size | ok | 0 | trade rows with size <= 0 |
| trade_book_same_timestamp_share | warn | 5.88235 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |
| trade_book_alignment | ok | 0 | trades not near matching side of BBO |
| trade_price_outside_visible_l2 | ok | 0 | trades outside visible L2 price range after backward book alignment |
| trade_book_alignment_age_ms | ok | 71.4157 | backward book alignment age stats={'p50_ms': 32.122438, 'p95_ms': 52.971629999999976, 'max_ms': 71.415698} |
| funding_rate_finite | ok | 0 | non-finite funding rates |
| funding_rate_outliers | ok | 0.000119434 | absolute funding p99=0.00011934, max=0.00011943 |
| funding_gaps | ok | 20 | gaps over threshold=0 |
| day_boundary_2026-03-19 | ok | 0 | rows outside source date |

### Audit Warning/Error Details

| check | severity | value | detail |
| --- | --- | --- | --- |
| trades_duplicate_timestamps | warn | 5 | duplicate timestamps; pct=29.4118 |
| one_tick_spread_share | warn | 79.8 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| trade_book_same_timestamp_share | warn | 5.88235 | trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books |

### Event Ordering Exposure

The default simulator policy processes trades before book updates when timestamps are exactly equal. Audit output quantifies exposure to the alternate book-before-trade convention; reproduce workflows also write `event_ordering_sensitivity.csv` with actual default-vs-alternate backtests.

| book_rows | trade_rows | trades_with_same_timestamp_book | trades_with_same_timestamp_book_pct | book_updates_with_same_timestamp_trade | book_updates_with_same_timestamp_trade_pct | default_equal_timestamp_policy | sensitivity_policy_to_review |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | 17 | 1 | 5.88235 | 1 | 0.1 | trade_before_book | book_before_trade |

### Spread Statistics

| tick_size | spread_min | spread_p05 | spread_p50 | spread_p95 | spread_p99 | spread_max | spread_ticks_p50 | one_tick_or_less_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.2 | 1 | 79.8 |

### Depth Statistics

| bid_depth_1_p50 | ask_depth_1_p50 | bid_depth_5_p50 | ask_depth_5_p50 | bid_depth_10_p50 | ask_depth_10_p50 | bid_depth_20_p50 | ask_depth_20_p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 38.908 | 35.227 | 130.12 | 161.73 | 220.597 | 253.698 | 641.835 | 756.01 |

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, fee-aware expected-edge gates, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior. Pressure and expected-edge stops are enforced at simulator level on existing live orders; fills during cancel latency are explicitly flagged.

## Results

- `total_pnl`: `0.0`
- `realized_trading_pnl`: `0.0`
- `unrealized_trading_pnl`: `0.0`
- `realized_roundtrip_pnl`: `0.0`
- `inventory_mtm_pnl`: `0.0`
- `funding_pnl`: `0.0`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `0.0`
- `forced_flat_pnl`: `0.0`
- `liquidation_cost`: `0.0`
- `final_liquidation_cost`: `0.0`
- `forced_flat_cost`: `0.0`
- `total_fills`: `0.0`
- `fill_volume_eth`: `0.0`
- `turnover_usd`: `0.0`
- `max_inventory`: `0.0`
- `min_inventory`: `0.0`
- `mean_abs_inventory`: `0.0`
- `max_drawdown`: `0.0`
- `sampled_1m_max_drawdown`: `-0.0`
- `sharpe_like_1m`: `0.0`
- `pnl_per_turnover`: `0.0`
- `pnl_per_eth`: `0.0`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | -0 |

## Round-Trip And Holding-Time Diagnostics

Rows pair fills greedily when inventory is reduced by an opposite-side fill. Long holding periods indicate inventory-path PnL rather than clean high-frequency spread economics.

### Round-Trip Concentration Summary

| closed_round_trips | total_roundtrip_pnl | positive_roundtrip_pnl | negative_roundtrip_pnl | top_roundtrip_pnl | top_roundtrip_pnl_share_pct | top_abs_roundtrip_pnl_share_pct | median_holding_seconds | p90_holding_seconds | max_holding_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Round-Trip Detail

_No rows._

### Holding-Time Distribution

_No rows._

## Fill Statistics

_No rows._

### Fill Diagnostic Breakdowns

_No rows._

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | order_observation_hours | placed_orders_per_hour | cancelled_orders_per_hour | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 39 | 0 | 37 | 0 | 0 | 0 | 0.948718 | pressure_stop_bid | 13 | 1.63288 | 4.37977 | 7.97506 | 0.0158701 | 2457.45 | 2331.43 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| pressure_stop_bid | 13 | 0 |
| expected_edge_ask | 12 | 0 |
| pressure_stop_ask | 5 | 0 |
| refresh_reprice | 4 | 0 |
| expected_edge_bid | 3 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

_No rows._

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Known Limitations

- The implemented bot strategy is simple and not proven live-deployable; use the run as backtest evidence and diagnostics, not as proof of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection and inventory-directional risk; positive simple-fill PnL is not alpha evidence when it comes from carrying directional inventory.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.
- The included dataset covers only three days, so fill counts, drawdown, and PnL are not statistically reliable strategy-performance estimates.

## Conclusion

The run finished with mid-marked total PnL `0.0000` USD, forced-flat PnL `0.0000` USD, realized trading PnL `0.0000` USD, unrealized trading PnL `0.0000` USD, and funding PnL `0.0000` USD. The strategy generated `0` fills and max drawdown `0.0000` USD under the selected fill model. Fill count is sparse and too small to support a statistically meaningful performance claim. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `round_trips.csv`, `round_trip_summary.csv`, `holding_time_distribution.csv`, `fee_sensitivity.csv`, `event_ordering_exposure.csv`
- Reproduction suite roots also include `fill_model_comparison.csv`, `event_ordering_sensitivity.csv`, and `run_scope.csv`.
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive round-trip PnL with negative short-horizon realized spreads should be read as inventory-path PnL, not clean spread economics. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
