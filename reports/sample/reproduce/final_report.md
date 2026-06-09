# ETH Perpetual Market-Making Reproduce Summary

This is an aggregate workflow report. Variant-specific backtest reports live under `baseline/`, `simple_fill/`, and `funding_disabled/`.

## Scope

- Suite size: `core`.
- Dataset scope: `sample_5000_rows`.

## Fill Model Comparison

| dataset_scope | variant | total_pnl | realized_trading_pnl | unrealized_trading_pnl | realized_roundtrip_pnl | inventory_mtm_pnl | funding_pnl | fees | liquidation_adjusted_pnl | forced_flat_pnl | liquidation_cost | final_liquidation_cost | forced_flat_cost | total_fills | fill_volume_eth | turnover_usd | max_inventory | min_inventory | mean_abs_inventory | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m | pnl_per_turnover | pnl_per_eth | avg_realized_spread_1s | avg_realized_spread_5s | avg_realized_spread_30s | pct_long | pct_short | inventory_pnl_share_abs | sparse_fill_warning | inventory_directional_warning | negative_realized_spread_warning | comparison_warnings | placed_orders | placed_orders_per_hour | top_roundtrip_pnl_share_pct | top_abs_roundtrip_pnl_share_pct | max_holding_seconds | fill_model | maker_fee_bps | cancel_latency_ms | queue_depletion_fraction | pressure_stop | min_half_spread_ticks | funding_target_frac | output_dir |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sample_5000_rows | baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 |  |  |  | 0 | 0 | 0 | True | False | False | sparse_fills | 148 | 1690.52 | 0 | 0 | 0 | conservative_queue | 0.5 | 250 | 0 | 0.5 | 2 | 0.25 | reports/sample/reproduce/baseline |
| sample_5000_rows | simple_fill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 |  |  |  | 0 | 0 | 0 | True | False | False | sparse_fills | 148 | 1690.52 | 0 | 0 | 0 | simple | 0.5 | 250 | 0 | 0.5 | 2 | 0.25 | reports/sample/reproduce/simple_fill |
| sample_5000_rows | funding_disabled | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 |  |  |  | 0 | 0 | 0 | True | False | False | sparse_fills | 140 | 1599.14 | 0 | 0 | 0 | conservative_queue | 0.5 | 250 | 0 | 0.5 | 2 | 0 | reports/sample/reproduce/funding_disabled |

## Event Ordering Sensitivity

| total_pnl | realized_trading_pnl | unrealized_trading_pnl | realized_roundtrip_pnl | inventory_mtm_pnl | funding_pnl | fees | liquidation_adjusted_pnl | forced_flat_pnl | liquidation_cost | final_liquidation_cost | forced_flat_cost | total_fills | fill_volume_eth | turnover_usd | max_inventory | min_inventory | mean_abs_inventory | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m | pnl_per_turnover | pnl_per_eth | variant | same_timestamp_policy | dataset_scope | trades_with_same_timestamp_book_pct | book_updates_with_same_timestamp_trade_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | trade_before_book | trade_before_book | sample_5000_rows | 13.5678 | 0.54 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | book_before_trade | book_before_trade | sample_5000_rows | 13.5678 | 0.54 |

## Ablations

| total_pnl | realized_trading_pnl | unrealized_trading_pnl | realized_roundtrip_pnl | inventory_mtm_pnl | funding_pnl | fees | liquidation_adjusted_pnl | forced_flat_pnl | liquidation_cost | final_liquidation_cost | forced_flat_cost | total_fills | fill_volume_eth | turnover_usd | max_inventory | min_inventory | mean_abs_inventory | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m | pnl_per_turnover | pnl_per_eth | variant | dataset_scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | full | sample_5000_rows |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | no_pressure_filter | sample_5000_rows |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | no_microprice_alpha | sample_5000_rows |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | no_inventory_skew | sample_5000_rows |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | no_funding_target | sample_5000_rows |

## Robustness

| total_pnl | realized_trading_pnl | unrealized_trading_pnl | realized_roundtrip_pnl | inventory_mtm_pnl | funding_pnl | fees | liquidation_adjusted_pnl | forced_flat_pnl | liquidation_cost | final_liquidation_cost | forced_flat_cost | total_fills | fill_volume_eth | turnover_usd | max_inventory | min_inventory | mean_abs_inventory | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m | pnl_per_turnover | pnl_per_eth | run | variant | dataset_scope | fill_model | pressure_stop | queue_depletion_fraction | cancel_latency_ms | maker_fee_bps | min_half_spread_ticks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 0 | baseline | sample_5000_rows | conservative_queue | 0.5 | 0 | 250 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 1 | simple_fill | sample_5000_rows | simple | 0.5 | 0 | 250 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 2 | partial_queue_0.25 | sample_5000_rows | partial_queue | 0.5 | 0.25 | 250 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 3 | partial_queue_0.50 | sample_5000_rows | partial_queue | 0.5 | 0.5 | 250 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 4 | cancel_latency_0 | sample_5000_rows | conservative_queue | 0.5 | 0 | 0 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 5 | cancel_latency_500 | sample_5000_rows | conservative_queue | 0.5 | 0 | 500 | 0.5 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 6 | fee_0bps | sample_5000_rows | conservative_queue | 0.5 | 0 | 250 | 0 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 7 | fee_1bps | sample_5000_rows | conservative_queue | 0.5 | 0 | 250 | 1 | 2 |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -0 | 0 | 0 | 0 | 8 | pressure_filter_off | sample_5000_rows | conservative_queue | 999 | 0 | 250 | 0.5 | 2 |

## Interpretation

Treat positive PnL as a backtest result to analyze, not a proven live edge. Sparse fills, negative short-horizon realized spread, high inventory-directional exposure, and partial-queue/fee failures are surfaced in the CSV warning columns when present.
