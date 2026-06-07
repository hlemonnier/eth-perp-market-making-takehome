# Top-of-Book Imbalance Signal Check

This check validates the default strategy change from a mixed book/trade pressure filter to a book-imbalance side filter. It uses only current book state at time `t` and measures future mid movement with `merge_asof` to the next observed book mark after each horizon.

Reproduce with:

```bash
python scripts/check_imbalance_signal.py
```

Signal definition:

```text
imbalance = (best_bid_qty - best_ask_qty) / (best_bid_qty + best_ask_qty)
signed_move_h = sign(imbalance_t) * (mid_{t+h} - mid_t)
```

For `abs(imbalance) >= 0.5`, the signal was positive on all three days:

| Horizon | Rows | Mean signed move | Hit rate | 2026-03-19 mean | 2026-03-20 mean | 2026-03-21 mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1s | 1,885,405 | 0.0674 | 27.17% | 0.0868 | 0.0740 | 0.0247 |
| 5s | 1,885,375 | 0.1295 | 45.92% | 0.1539 | 0.1422 | 0.0688 |
| 30s | 1,885,182 | 0.1966 | 54.87% | 0.2057 | 0.1955 | 0.1833 |

Interpretation:

- The median is often near zero because book updates are dense and many short-horizon marks do not move.
- The 5s and 30s means are consistently positive across all days, so the signal is not a single-day artifact.
- The strategy uses this as an adverse-selection filter: when book imbalance is strongly one-sided, it stops quoting the side most likely to be picked off rather than aggressively crossing or chasing the move.
- The simple-fill model remains an aggressive stress test. It assumes much easier fills than the conservative queue model and is not the target execution model for this maker-only strategy.

Literature anchor:

- Gould and Bonart, ["Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book"](https://arxiv.org/abs/1512.03492), documents queue imbalance as a statistically meaningful predictor of the next mid-price move.
- Cont, Kukanov, and Stoikov, ["The Price Impact of Order Book Events"](https://arxiv.org/abs/1011.6402), finds that short-horizon price changes are strongly linked to order-flow imbalance at the best bid and ask.
