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

### Event Ordering Sensitivity

The simulator processes trades before book updates when timestamps are exactly equal. This table quantifies how much data is exposed to the alternate book-before-trade convention.

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

- `total_pnl`: `104.93537761108074`
- `realized_trading_pnl`: `0.6468657944613234`
- `unrealized_trading_pnl`: `104.7409630889897`
- `realized_roundtrip_pnl`: `0.6468657944613234`
- `inventory_mtm_pnl`: `104.7409630889897`
- `funding_pnl`: `-0.19827149423776644`
- `fees`: `0.25417977813271275`
- `liquidation_adjusted_pnl`: `104.88537761108056`
- `forced_flat_pnl`: `104.78114261108031`
- `liquidation_cost`: `0.0500000000001819`
- `final_liquidation_cost`: `0.0500000000001819`
- `forced_flat_cost`: `0.15423500000042623`
- `total_fills`: `42.0`
- `fill_volume_eth`: `2.3097583507189685`
- `turnover_usd`: `5083.5955626542545`
- `max_inventory`: `0.21013686430570033`
- `min_inventory`: `-1.0`
- `mean_abs_inventory`: `0.851452258688288`
- `max_drawdown`: `63.08555043634705`
- `sampled_1m_max_drawdown`: `57.340261139670474`
- `sharpe_like_1m`: `0.6592907906021914`
- `pnl_per_turnover`: `0.020641960265676943`
- `pnl_per_eth`: `45.43132296866339`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | 49.6273 | 49.6273 | 0.646866 | 49.4145 | -0.197753 | 0.236277 | 0.646866 | 49.4145 | -0.197753 | 0.236277 | 7 | 25 | 0.654879 | 1.48855 | -0.573836 | 0.833666 | 42.9322 | 39.5441 |
| 2026-03-20 | 49.6273 | 42.0036 | -7.62371 | 0 | -7.21699 | -0.391093 | 0.015623 | 0.646866 | 42.1975 | -0.588846 | 0.2519 | 0 | 9 | 0 | 0.145118 | -0.950351 | 0.978784 | 53.2916 | 49.5206 |
| 2026-03-21 | 42.0036 | 104.935 | 62.9318 | 0 | 62.5435 | 0.390574 | 0.00227984 | 0.646866 | 104.741 | -0.198271 | 0.25418 | 0 | 1 | 0 | 0.0212157 | -0.998292 | 1 | 23.5634 | 22.576 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid | pressure_stop_violation_fills | pending_cancel_fills | pending_cancel_pressure_fills | live_fills | live_avg_realized_spread_5s | pending_cancel_avg_realized_spread_5s | average_quote_age_ms | average_book_age_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | 2.30976 | 7 | 35 | 0.0549942 | 0.0422269 | 121.038 | 0.238095 | 0 | 39 | 30 | 3 | -0.0833333 | -0.591026 | 2377.38 | 27.0128 |

### Fill Diagnostic Breakdowns

| breakdown | bucket | fills | avg_realized_spread_5s | avg_markout_1s | avg_quote_age_ms |
| --- | --- | --- | --- | --- | --- |
| side | ask | 35 | -0.501429 | 0.685714 | 2546.02 |
| side | bid | 7 | -0.821429 | -0.571429 | 1534.17 |
| pressure_bucket | (-0.25, 0.25] | 5 | -0.85 | 0.94 | 1820.46 |
| pressure_bucket | (-0.5, -0.25] | 2 | -0.2 | 0.35 | 3333.43 |
| pressure_bucket | (-0.75, -0.5] | 2 | -0.15 | -0.525 | 1042.9 |
| pressure_bucket | (-1.011, -0.75] | 4 | -0.55 | -0.7875 | 1122.42 |
| pressure_bucket | (0.25, 0.5] | 4 | -0.5 | 0.275 | 1313.59 |
| pressure_bucket | (0.5, 0.75] | 5 | 0.01 | 0.02 | 1361.89 |
| pressure_bucket | (0.75, 1.01] | 20 | -0.71 | 0.88 | 3272.08 |
| quote_age_bucket_ms | 1000-5000 | 23 | -0.276087 | 0.341304 | 2004.02 |
| quote_age_bucket_ms | 250-1000 | 13 | -1.21923 | 0.457692 | 516.194 |
| quote_age_bucket_ms | 5000-30000 | 6 | -0.183333 | 1.03333 | 7841.16 |
| queue_ahead_bucket | 20+ | 42 | -0.554762 | 0.47619 | 2377.38 |
| inventory_bucket | flat | 3 | -1.48333 | 0.0666667 | 1018.46 |
| inventory_bucket | long_small | 6 | -0.483333 | -0.05 | 1409 |
| inventory_bucket | short_large | 23 | -0.48913 | 0.895652 | 3306.95 |
| inventory_bucket | short_small | 10 | -0.47 | -0.05 | 1228.08 |
| spread_bucket | 0.1-0.5 | 8 | -0.25 | 0.23125 | 1399.66 |
| spread_bucket | 0.5-1 | 4 | -1.15 | 1.0125 | 2699.17 |
| spread_bucket | 2+ | 1 | -1.35 | 0.7 | 1122.9 |
| spread_bucket | <=0.1 | 29 | -0.52931 | 0.462069 | 2645.97 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 24174 | 42 | 24132 | 514 | 0.0017374 | 0.0017374 | 0.998263 | pressure_stop_ask | 10553 | 2.70102 | 10.25 | 10.25 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| pressure_stop_ask | 10553 | 0 |
| refresh_reprice | 9713 | 0 |
| quote_age_expired | 1463 | 0 |
| pressure_stop_bid | 1287 | 0 |
| expected_edge_ask | 677 | 0 |
| expected_edge_bid | 379 | 0 |
| stale_book | 35 | 0 |
| expected_edge_jump_cooldown | 19 | 0 |
| refresh_no_desired_quote | 3 | 0 |
| quote_crossed_after_book_update | 2 | 0 |
| eod_reduce_only | 1 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.840863 | 0.851452 | 0.254455 | -1 | 0.210137 | 4.46656 | 95.3946 | 0.138857 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 3581577 | -0.428571 | 0.666667 | 22.0822 | 70.593 |
| 5 | event_level_book | 3581577 | -0.554762 | 0.792857 | 28.446 | 94.8304 |
| 30 | event_level_book | 3581577 | -0.57619 | 0.814286 | 30.8284 | 129.879 |

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -0.25418 | 105.444 | 0.901046 | 63.0856 | 42 | 5083.6 | 0.020742 |
| 0 | 0 | 105.19 | 0.646866 | 63.0856 | 42 | 5083.6 | 0.020692 |
| 0.5 | 0.25418 | 104.935 | 0.392686 | 63.0856 | 42 | 5083.6 | 0.020642 |
| 1 | 0.50836 | 104.681 | 0.138506 | 63.0856 | 42 | 5083.6 | 0.020592 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection; it is not a better-performance upper bound.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.

## Conclusion

The run finished with mid-marked total PnL `104.9354` USD, forced-flat PnL `104.7811` USD, realized trading PnL `0.6469` USD, unrealized trading PnL `104.7410` USD, and funding PnL `-0.1983` USD. The strategy generated `42` fills and max drawdown `63.0856` USD under the selected fill model. Most reported PnL is mark-to-market inventory PnL rather than realized spread capture, so the result should be treated as a conservative simulator validation, not proof of robust market-making edge.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`, `event_ordering_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive forced-flat PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
