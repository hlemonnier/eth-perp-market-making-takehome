# Fill Model Comparison

| fill_model | total_pnl | realized_trading_pnl | unrealized_trading_pnl | funding_pnl | total_fills | fill_volume_eth | max_drawdown | sampled_1m_max_drawdown | sharpe_like_1m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conservative_queue | -6.66744 | -12.8475 | 5.93689 | 0.243211 | 27 | 2.87169 | 22.0486 | 21.1183 | -0.212922 |
| simple | -30.361 | -30.6956 | 0 | 0.334617 | 894 | 80.7059 | 35.5881 | 35.4229 | -0.798997 |

The conservative queue-ahead result is the official baseline because L2 snapshots and prints do not reveal true queue position. The simple fill result removes queue-ahead and is optimistic about priority, but it increases exposure to toxic fills; interpret it as an aggressive-fill sensitivity, not a better-performance upper bound.
