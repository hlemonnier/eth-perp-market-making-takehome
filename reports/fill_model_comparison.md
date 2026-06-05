# Fill Model Comparison

| fill_model | total_pnl | realized_trading_pnl | unrealized_trading_pnl | funding_pnl | total_fills | fill_volume_eth | max_drawdown | sharpe_like_1m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conservative_queue | 12.82 | 0.0548299 | 12.6629 | 0.10226 | 6 | 0.539489 | 4.82419 | 0.895003 |
| simple | -10.1749 | -9.82669 | -0.623579 | 0.275345 | 85 | 8.54093 | 22.4381 | -0.263117 |

The conservative queue-ahead result is the official baseline. The simple fill result is an optimistic sensitivity that removes queue-ahead and should not be treated as the main performance claim.
