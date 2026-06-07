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
- Git commit: `cdff6a3`.

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
| spread_distribution | ok | 0.1 | stats={'tick_size': 0.1, 'spread_min': 0.09999999999990905, 'spread_p05': 0.09999999999990905, 'spread_p50': 0.09999999999990905, 'spread_p95': 0.1000000000003638, 'spread_p99': 0.1000000000003638, 'spread_max': 2.700000000000273, 'spread_ticks_p50': 0.9999999999990905, 'one_tick_or_less_pct': 80.49914883862611} |
| one_tick_spread_share | warn | 80.4991 | share of books with spread <= one inferred tick; high values leave little edge after fees/queue |
| mid_jump_outliers | warn | 48 | mid jump ticks p99=2.0000, max=48.0000 |
| depth_distribution | ok | 33.402 | stats={'bid_depth_1_p50': 33.402, 'ask_depth_1_p50': 32.717, 'bid_depth_5_p50': 147.01999999999998, 'ask_depth_5_p50': 150.068, 'bid_depth_10_p50': 257.80499999999995, 'ask_depth_10_p50': 282.256, 'bid_depth_20_p50': 721.3970000000002, 'ask_depth_20_p50': 704.3689999999999} |
| trade_price_size_finite | ok | 0 | non-finite trade price or size |
| trade_side_values | ok | 0 | is_maker_ask values outside {0,1} |
| trade_positive_size | ok | 0 | trade rows with size <= 0 |
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
| trade_book_alignment | warn | 579 | trades not near matching side of BBO |
| trade_book_alignment_age_ms | warn | 33439.9 | backward book alignment age stats={'p50_ms': 27.204994, 'p95_ms': 87.6368175, 'max_ms': 33439.860910999996} |

### Spread Statistics

| tick_size | spread_min | spread_p05 | spread_p50 | spread_p95 | spread_p99 | spread_max | spread_ticks_p50 | one_tick_or_less_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 2.7 | 1 | 80.4991 |

### Depth Statistics

| bid_depth_1_p50 | ask_depth_1_p50 | bid_depth_5_p50 | ask_depth_5_p50 | bid_depth_10_p50 | ask_depth_10_p50 | bid_depth_20_p50 | ask_depth_20_p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 33.402 | 32.717 | 147.02 | 150.068 | 257.805 | 282.256 | 721.397 | 704.369 |

## Strategy

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior.

## Results

- `total_pnl`: `-21.3883669900808`
- `realized_trading_pnl`: `-25.923181572758356`
- `unrealized_trading_pnl`: `4.216547135813019`
- `funding_pnl`: `0.3182674468645925`
- `fees`: `0.0`
- `liquidation_adjusted_pnl`: `-21.391854622120366`
- `total_fills`: `427.0`
- `fill_volume_eth`: `40.43474756054843`
- `turnover_usd`: `86980.9381556926`
- `max_inventory`: `0.525890681235401`
- `min_inventory`: `-0.4955910144242508`
- `mean_abs_inventory`: `0.1554516791318588`
- `max_drawdown`: `34.7629995206499`
- `sampled_1m_max_drawdown`: `33.27285449913289`
- `sharpe_like_1m`: `-0.5652240645578059`
- `pnl_per_turnover`: `-0.00024589717521552175`
- `pnl_per_eth`: `-0.5289600722263221`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -21.5301 | -21.5301 | -21.6036 | 0 | 0.0735206 | 0 | -21.6036 | 0 | 0.0735206 | 0 | 98 | 94 | 9.2279 | 9.2279 | 0.070514 | 0.525891 | 28.3842 |
| 2026-03-20 | -21.5301 | -23.955 | -2.42494 | -3.01343 | 0.45043 | 0.13806 | 0 | -24.6171 | 0.45043 | 0.21158 | 0 | 74 | 80 | 7.01557 | 7.17875 | 0.133122 | 0.519891 | 14.6359 |
| 2026-03-21 | -23.955 | -21.3884 | 2.56668 | -1.30612 | 3.76612 | 0.106687 | 0 | -25.9232 | 4.21655 | 0.318267 | 0 | 41 | 40 | 3.93903 | 3.8456 | -0.106601 | 0.495591 | 6.05758 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 427 | 40.4347 | 213 | 214 | 0.094695 | 0.0997292 | 203.702 | 0.282787 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 103525 | 405 | 103166 | 3721 | 0.00412461 | 0.0039121 | 0.996532 | refresh_reprice | 57411 | 3.57357 | 10 | 10 | 15446 | 14.972 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| refresh_reprice | 57411 | 12288 |
| refresh_no_desired_quote | 26878 | 2934 |
| quote_age_expired | 16619 | 0 |
| quote_crossed_after_book_update | 2115 | 150 |
| jump_cooldown | 140 | 74 |
| eod_reduce_only | 3 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0323128 | 0.155452 | 0.190398 | -0.495591 | 0.525891 | 60.2175 | 39.389 | 0.393427 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 3581577 | -0.353279 | 0.636066 | 28.9089 | 23925.3 |
| 5 | event_level_book | 3581577 | -0.369672 | 0.652459 | 36.6752 | 19925.3 |
| 30 | event_level_book | 3581577 | -0.276581 | 0.559368 | 33.9082 | 764.427 |

## Maker Fee Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_pnl_per_turnover |
| --- | --- | --- | --- |
| 0 | 0 | -21.3884 | -0.000245897 |
| 1 | 8.69809 | -30.0865 | -0.000345897 |
| 2 | 17.3962 | -38.7846 | -0.000445897 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order.
- The simple fill model is intentionally aggressive and stress-tests adverse selection; it is not a better-performance upper bound.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.

## Conclusion

The run finished with total PnL `-21.3884` USD, realized trading PnL `-25.9232` USD, unrealized trading PnL `4.2165` USD, and funding PnL `0.3183` USD. The strategy generated `427` fills and max drawdown `34.7630` USD under the selected fill model. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. Overall max drawdown is event-level; daily drawdown is a report-frequency diagnostic. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
