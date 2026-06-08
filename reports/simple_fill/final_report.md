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
- Git commit: `a10ec85`.

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

Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior. Pressure stops are enforced at simulator level on existing live orders; fills during cancel latency are explicitly flagged.

## Results

- `total_pnl`: `-40.762714850470715`
- `realized_trading_pnl`: `-34.179661177151495`
- `unrealized_trading_pnl`: `0.0`
- `spread_capture_pnl`: `-34.179661177151495`
- `inventory_mtm_pnl`: `0.0`
- `funding_pnl`: `0.26895058946439065`
- `fees`: `6.852004262781115`
- `liquidation_adjusted_pnl`: `-40.762714850470715`
- `forced_flat_pnl`: `-40.762714850470715`
- `liquidation_cost`: `0.0`
- `final_liquidation_cost`: `0.0`
- `forced_flat_cost`: `0.0`
- `total_fills`: `679.0`
- `fill_volume_eth`: `63.74591265614714`
- `turnover_usd`: `137040.08525562234`
- `max_inventory`: `0.5875883938715449`
- `min_inventory`: `-0.592026099352432`
- `mean_abs_inventory`: `0.16103815645131134`
- `max_drawdown`: `46.582658316280984`
- `sampled_1m_max_drawdown`: `46.388368260960554`
- `sharpe_like_1m`: `-1.0764662286356643`
- `pnl_per_turnover`: `-0.0002974510324802819`
- `pnl_per_eth`: `-0.6394561337657763`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | -30.2924 | -30.2924 | -27.0733 | 0 | 0.0692126 | 3.28835 | -27.0733 | 0 | 0.0692126 | 3.28835 | 164 | 166 | 15.2493 | 15.2493 | 0.0987967 | 0.592026 | 41.3428 | 40.8305 |
| 2026-03-20 | -30.2924 | -40.0499 | -9.75751 | -7.22581 | 0.00258107 | 0.0946629 | 2.62894 | -34.2991 | 0.00258107 | 0.163875 | 5.91729 | 131 | 127 | 12.2576 | 12.3092 | 0.0956744 | 0.57041 | 16.2854 | 16.1175 |
| 2026-03-21 | -40.0499 | -40.7627 | -0.712815 | 0.119404 | -0.00258107 | 0.105075 | 0.934714 | -34.1797 | 0 | 0.268951 | 6.852 | 48 | 43 | 4.3661 | 4.31448 | -0.107045 | 0.56017 | 6.852 | 6.67166 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid | pressure_stop_violation_fills | average_quote_age_ms | average_book_age_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 679 | 63.7459 | 343 | 336 | 0.0938821 | 0.0983616 | 201.826 | 0.125405 | 0 | 2681.18 | 28.3283 |

### Fill Diagnostic Breakdowns

| breakdown | bucket | fills | avg_realized_spread_5s | avg_markout_1s | avg_quote_age_ms |
| --- | --- | --- | --- | --- | --- |
| side | ask | 336 | -0.444048 | 0.500149 | 2650.17 |
| side | bid | 343 | -0.382799 | -0.481487 | 2711.55 |
| pressure_bucket | (-0.25, 0.25] | 87 | -0.148276 | -0.0218391 | 2692.52 |
| pressure_bucket | (-0.5, -0.25] | 44 | -0.590909 | -0.0340909 | 2564.08 |
| pressure_bucket | (-0.75, -0.5] | 50 | -0.54 | -0.607 | 2574.1 |
| pressure_bucket | (-1.011, -0.75] | 209 | -0.39689 | -0.529426 | 2756.12 |
| pressure_bucket | (0.25, 0.5] | 46 | -0.147826 | 0.143478 | 2995.74 |
| pressure_bucket | (0.5, 0.75] | 51 | -0.25 | 0.190196 | 2456.4 |
| pressure_bucket | (0.75, 1.01] | 192 | -0.583854 | 0.682292 | 2633.53 |
| quote_age_bucket_ms | 1000-5000 | 325 | -0.357692 | -0.0123077 | 2459.67 |
| quote_age_bucket_ms | 250-1000 | 227 | -0.466079 | 0.0462555 | 549.607 |
| quote_age_bucket_ms | 5000-30000 | 127 | -0.460236 | -0.0283465 | 7058 |
| queue_ahead_bucket | 20+ | 671 | -0.41535 | 0.00275708 | 2697.82 |
| queue_ahead_bucket | 5-20 | 8 | -0.225 | 0.13125 | 1285.13 |
| inventory_bucket | flat | 123 | -0.476829 | -0.0422764 | 2470.17 |
| inventory_bucket | long_large | 5 | -1.19 | 0.08 | 1040.83 |
| inventory_bucket | long_small | 382 | -0.395157 | 0.0230366 | 2495.87 |
| inventory_bucket | short_large | 8 | -0.6 | -0.13125 | 968.224 |
| inventory_bucket | short_small | 161 | -0.373602 | -0.000310559 | 3418.11 |
| spread_bucket | 0.1-0.5 | 183 | -0.299727 | -0.00245902 | 2357.49 |
| spread_bucket | 0.5-1 | 26 | -1.18846 | 0.282692 | 1737.9 |
| spread_bucket | 1-2 | 1 | -2.65 | -3.5 | 253.438 |
| spread_bucket | <=0.1 | 469 | -0.409595 | -0.0010661 | 2864.95 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 118273 | 638 | 117673 | 3683 | 0.00574096 | 0.0053943 | 0.994927 | refresh_reprice | 43836 | 2.88771 | 10.25 | 10.25 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| refresh_reprice | 43836 | 0 |
| pressure_stop_ask | 30824 | 0 |
| pressure_stop_bid | 30126 | 0 |
| quote_age_expired | 12120 | 0 |
| stale_book | 601 | 0 |
| quote_crossed_after_book_update | 100 | 0 |
| jump_cooldown | 63 | 0 |
| eod_reduce_only | 3 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0291105 | 0.161038 | 0.200028 | -0.592026 | 0.587588 | 59.0835 | 40.361 | 0.555427 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 3581577 | -0.365317 | 0.490722 | 28.1535 | 277.647 |
| 5 | event_level_book | 3581577 | -0.413108 | 0.538513 | 33.1412 | 544.376 |
| 30 | event_level_book | 3581577 | -0.5081 | 0.633505 | 34.411 | 764.427 |

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -6.852 | -27.0587 | -27.3277 | 46.5827 | 679 | 137040 | -0.000197451 |
| 0 | 0 | -33.9107 | -34.1797 | 46.5827 | 679 | 137040 | -0.000247451 |
| 0.5 | 6.852 | -40.7627 | -41.0317 | 46.5827 | 679 | 137040 | -0.000297451 |
| 1 | 13.704 | -47.6147 | -47.8837 | 46.5827 | 679 | 137040 | -0.000347451 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection; it is not a better-performance upper bound.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.

## Conclusion

The run finished with mid-marked total PnL `-40.7627` USD, forced-flat PnL `-40.7627` USD, realized trading PnL `-34.1797` USD, unrealized trading PnL `0.0000` USD, and funding PnL `0.2690` USD. The strategy generated `679` fills and max drawdown `46.5827` USD under the selected fill model. Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive forced-flat PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
