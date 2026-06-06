# Fill Model Comparison

| fill_model | total_pnl | realized_trading_pnl | unrealized_trading_pnl | funding_pnl | total_fills | fill_volume_eth | turnover_usd | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conservative_queue | 7.79738 | 6.18459 | 1.46457 | 0.148222 | 23 | 2.47536 | 5354.44 | 5.9235 | 5.82619 | 0.425645 |
| simple | -44.4011 | -44.738 | 0 | 0.336838 | 916 | 83.0045 | 178608 | 48.7482 | 48.5261 | -1.24654 |

The conservative queue-ahead result is the official baseline because L2 snapshots and prints do not reveal true queue position. The simple fill result removes queue-ahead and is optimistic about priority, but it increases exposure to toxic fills; interpret it as an aggressive-fill sensitivity, not a better-performance upper bound.

The baseline should still be framed as a simulator-validation result. The simple-fill run remains negative and the realized-spread diagnostics use event-level book-update marks, so the comparison is evidence of adverse selection rather than proof of robust market-making edge.
