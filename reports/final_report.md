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

- `total_pnl`: `16.433068787612825`
- `realized_trading_pnl`: `16.379406517981128`
- `unrealized_trading_pnl`: `0.22567549321381478`
- `spread_capture_pnl`: `16.379406517981128`
- `inventory_mtm_pnl`: `0.22567549321381478`
- `funding_pnl`: `-0.03740779755331261`
- `fees`: `0.13460542602869996`
- `liquidation_adjusted_pnl`: `16.432893411082482`
- `forced_flat_pnl`: `16.432527803629675`
- `liquidation_cost`: `0.00017537653034338518`
- `final_liquidation_cost`: `0.00017537653034338518`
- `forced_flat_cost`: `0.0005409839831500562`
- `total_fills`: `11.0`
- `fill_volume_eth`: `1.2482253124566867`
- `turnover_usd`: `2692.108520573999`
- `max_inventory`: `0.1291675488245164`
- `min_inventory`: `-0.19646804617692137`
- `mean_abs_inventory`: `0.06815915162652808`
- `max_drawdown`: `9.66901739988533`
- `sampled_1m_max_drawdown`: `9.275677579005606`
- `sharpe_like_1m`: `0.8850567652357276`
- `pnl_per_turnover`: `0.0061041628381715615`
- `pnl_per_eth`: `13.16514624693052`

## Daily PnL

| date | starting_equity | ending_equity | daily_pnl | daily_realized_trading_pnl | daily_unrealized_trading_pnl_change | daily_funding_pnl | daily_fees | ending_realized_trading_pnl | ending_unrealized_trading_pnl | ending_funding_pnl | ending_fees | bid_fills | ask_fills | bid_volume_eth | ask_volume_eth | average_inventory | max_abs_inventory | max_drawdown | sampled_1m_max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-19 | 0 | 12.1294 | 12.1294 | 8.20579 | 4.01516 | -0.0544504 | 0.0371395 | 8.20579 | 4.01516 | -0.0544504 | 0.0371395 | 1 | 2 | 0.142966 | 0.196468 | -0.100571 | 0.196468 | 9.66902 | 9.27568 |
| 2026-03-20 | 12.1294 | 17.1194 | 4.99004 | 9.06489 | -4.00079 | -0.00303064 | 0.0710298 | 17.2707 | 0.0143729 | -0.057481 | 0.108169 | 3 | 3 | 0.357464 | 0.305704 | -0.012167 | 0.155553 | 6.91241 | 6.42328 |
| 2026-03-21 | 17.1194 | 16.4331 | -0.686326 | -0.891266 | 0.211303 | 0.0200732 | 0.0264361 | 16.3794 | 0.225675 | -0.0374078 | 0.134605 | 1 | 1 | 0.121929 | 0.123694 | -0.0408494 | 0.125436 | 1.75678 | 1.74424 |

## Fill Statistics

| fill_count | fill_volume_eth | bid_fills | ask_fills | mean_fill_size | median_fill_size | average_fill_notional | average_passive_edge_to_mid | pressure_stop_violation_fills | average_quote_age_ms | average_book_age_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 1.24823 | 5 | 6 | 0.113475 | 0.121165 | 244.737 | 0.0227273 | 0 | 3376.45 | 47.5805 |

### Fill Diagnostic Breakdowns

| breakdown | bucket | fills | avg_realized_spread_5s | avg_markout_1s | avg_quote_age_ms |
| --- | --- | --- | --- | --- | --- |
| side | ask | 6 | -0.616667 | 0.583333 | 2997.91 |
| side | bid | 5 | -0.73 | -0.78 | 3830.7 |
| pressure_bucket | (-0.25, 0.25] | 4 | 0.05 | 0.125 | 2928.48 |
| pressure_bucket | (-0.75, -0.5] | 2 | -1.2 | -1.25 | 1629 |
| pressure_bucket | (-1.011, -0.75] | 1 | -0.15 | -0.4 | 6993.35 |
| pressure_bucket | (0.25, 0.5] | 2 | -0.55 | -0.5 | 4451.07 |
| pressure_bucket | (0.5, 0.75] | 1 | -0.35 | 0.2 | 913.919 |
| pressure_bucket | (0.75, 1.01] | 1 | -3.55 | 2.8 | 5359.63 |
| quote_age_bucket_ms | 1000-5000 | 6 | -0.266667 | -0.166667 | 2820.13 |
| quote_age_bucket_ms | 250-1000 | 2 | -1 | -0.7 | 945.113 |
| quote_age_bucket_ms | 5000-30000 | 3 | -1.25 | 0.666667 | 6109.99 |
| queue_ahead_bucket | 20+ | 11 | -0.668182 | -0.0363636 | 3376.45 |
| inventory_bucket | flat | 3 | -0.383333 | -0.1 | 2879.76 |
| inventory_bucket | long_small | 1 | -0.35 | 0.2 | 913.919 |
| inventory_bucket | short_small | 7 | -0.835714 | -0.0428571 | 3941.11 |
| spread_bucket | 0.1-0.5 | 4 | -0.55 | -0.375 | 2737.27 |
| spread_bucket | <=0.1 | 7 | -0.735714 | 0.157143 | 3741.7 |

## Order Statistics

| placed_orders | filled_orders | cancelled_orders | resized_orders | fill_to_order_ratio | filled_order_ratio | cancel_to_order_ratio | top_cancel_reason | top_cancel_reason_count | average_quote_lifetime_seconds | p95_quote_lifetime_seconds | max_quote_lifetime_seconds | cancelled_before_active_orders | pct_orders_cancelled_before_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 118041 | 11 | 118029 | 3705 | 9.3188e-05 | 9.3188e-05 | 0.999898 | refresh_reprice | 43603 | 2.89618 | 10.25 | 10.25 | 0 | 0 |

### Order Cancellation Reasons

| reason | cancelled_orders | cancelled_before_active_orders |
| --- | --- | --- |
| refresh_reprice | 43603 | 0 |
| pressure_stop_ask | 30910 | 0 |
| pressure_stop_bid | 30509 | 0 |
| quote_age_expired | 12169 | 0 |
| stale_book | 594 | 0 |
| quote_crossed_after_book_update | 173 | 0 |
| jump_cooldown | 69 | 0 |
| eod_reduce_only | 2 | 0 |

## Inventory Statistics

| mean_inventory | mean_abs_inventory | std_inventory | min_inventory | max_inventory | pct_long | pct_short | pct_flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.0511935 | 0.0681592 | 0.0815512 | -0.196468 | 0.129168 | 18.0514 | 77.4821 | 4.46656 |

## Realized Spread and Adverse Selection

Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.

| horizon_seconds | mark_source | marks_available | average_realized_spread | average_toxicity | median_mark_lookup_lag_ms | max_mark_lookup_lag_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | event_level_book | 3581577 | -0.65 | 0.672727 | 21.0151 | 51.9933 |
| 5 | event_level_book | 3581577 | -0.668182 | 0.690909 | 59.6263 | 213.023 |
| 30 | event_level_book | 3581577 | -0.431818 | 0.454545 | 56.5985 | 129.879 |

## Maker Fee/Rebate Sensitivity

| maker_fee_bps | estimated_fees | estimated_total_pnl | estimated_realized_pnl | max_drawdown | fills | turnover_usd | estimated_pnl_per_turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.5 | -0.134605 | 16.7023 | 16.514 | 9.66902 | 11 | 2692.11 | 0.00620416 |
| 0 | 0 | 16.5677 | 16.3794 | 9.66902 | 11 | 2692.11 | 0.00615416 |
| 0.5 | 0.134605 | 16.4331 | 16.2448 | 9.66902 | 11 | 2692.11 | 0.00610416 |
| 1 | 0.269211 | 16.2985 | 16.1102 | 9.66902 | 11 | 2692.11 | 0.00605416 |

## Known Limitations

- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.
- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.
- The simple fill model is intentionally aggressive and stress-tests adverse selection; it is not a better-performance upper bound.
- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.

## Conclusion

The run finished with mid-marked total PnL `16.4331` USD, forced-flat PnL `16.4325` USD, realized trading PnL `16.3794` USD, unrealized trading PnL `0.2257` USD, and funding PnL `-0.0374` USD. The strategy generated `11` fills and max drawdown `9.6690` USD under the selected fill model. Realized trading PnL is positive, which is stronger evidence of spread capture than total PnL alone.


## Output Files

- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`
- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`
- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `fee_sensitivity.csv`
- `config_used.yaml`
- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`

## Interpretation Discipline

Use the PnL decomposition rather than total PnL alone. Positive forced-flat PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.
