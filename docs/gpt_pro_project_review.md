Overall verdict: **do not submit yet as-is**.

After a short patch pass, this becomes **submit with caveats**. The project is structurally solid, honest, and much better than a generic market-making take-home, but there are enough correctness/reporting issues that a sharp quant reviewer could poke holes in it quickly. The biggest problem is not that the strategy loses under simple fills or only has six conservative fills. The biggest problem is that a few implementation details make the current report look more polished than the evidence supports.

I ran the unit tests: **14 passed**. I inspected the source, config, generated reports, fills/orders/equity outputs, and the project document. I did not rerun the full parquet backtest from raw data in this container because the environment lacks a parquet engine such as `pyarrow`; the review below is based on the source code and committed report artifacts.

Separate verdicts:

Math/modeling: **conditional pass**. The fair value, microprice, inventory skew, funding target, and adverse-selection logic are coherent, but the strategy is not empirically convincing and the volatility model is weak.

Simulator realism: **conditional pass, leaning weak**. The event ordering and queue-ahead model are defensible, but the fill evidence is too thin and the current queue/cancel behavior makes the conservative baseline almost non-trading.

PnL accounting: **mostly pass**, but with important reporting bugs. Core cash/inventory/average-cost accounting looks correct. Daily PnL decomposition is not correct because cumulative realized/funding/fee values are shown as daily values.

Code quality: **conditional pass**. The architecture is clean and modular. However, there are some avoidable issues: float tick rounding, unused config fields, hard-coded report text, weak audit duplicate detection, and incorrect order-cancel timestamps.

Tests: **conditional pass**. The toy tests are useful and pass, but they do not cover the failure modes that matter most for a trading simulator.

Report quality: **conditional pass**. It is honest about mark-to-market inventory PnL, which is good. But it needs stronger caveats, more audit detail, fee sensitivity, daily incremental PnL splits, and a clearer statement that this is a simulator-validation baseline, not a profitable market-making strategy.

1. Blunt submission verdict

**As-is: do not submit yet.**

The codebase is close, but I would not submit this exact version for a quant/trading engineering role because a reviewer can immediately criticize:

The conservative baseline has only **6 fills in 3 days**, so there is essentially no statistical evidence of market-making edge.

The positive PnL is almost entirely **unrealized inventory PnL**: about `12.66` out of `12.82` USD.

The simple fill sensitivity loses money with **85 fills** and negative realized PnL, which is a strong adverse-selection warning.

The report says the simple-fill run uses the conservative queue-ahead model because the report text is hard-coded.

The daily realized/unrealized/funding table is misleading because some columns are cumulative end-of-day values, not daily increments.

There is a real float tick-rounding bug in `strategy.py`.

The EOD reduce-only logic is not actually reduce-only in all cases.

With 2 hours of fixes, I would change the verdict to **submit with caveats**. With 1–3 days, it can become a genuinely strong submission.

2. Does it respect `market_making_blueprint.md`?

Mostly yes, structurally. The module layout closely follows the blueprint:

`data_loader.py`, `data_audit.py`, `book_state.py`, `features.py`, `strategy.py`, `fill_model.py`, `accounting.py`, `risk.py`, `simulator.py`, `metrics.py`, and `reporting.py` map cleanly to the intended design.

The main mismatches are important:

`src/market_maker/strategy.py`: `requote_delta_ticks` and `funding_retarget_threshold` are in config but are not actually used in `_should_refresh`. The blueprint explicitly included refresh when quote distance or funding target changes materially.

`src/market_maker/risk.py` and `strategy.py`: EOD reduce-only does not guarantee reduce-only. If inventory is flat, the strategy can still open a new position during the reduce-only window. If inventory is small, a quote can reduce and flip the position.

`src/market_maker/metrics.py`: daily PnL is correct, but daily realized/funding/fees columns are cumulative, not daily increments.

`src/market_maker/reporting.py`: the report hard-codes “Official result uses the conservative queue-ahead fill model,” even for `reports/simple_fill/final_report.md`.

`src/market_maker/data_audit.py`: duplicate row detection is flawed because `_row_id` is included in `df.duplicated()`, making exact duplicate market rows almost impossible to detect.

`src/market_maker/data_audit.py`: the blueprint called for outlier price/size checks. The implementation has only limited alignment/spread/depth checks, not robust outlier detection.

`src/market_maker/features.py`: volatility is not time-normalized and is polluted by repeated mid updates at trade/funding timestamps. That does not match the blueprint’s more defensible volatility-buffer design.

`src/market_maker/simulator.py`: metrics are computed from a 1-minute reported equity curve, not full event-level equity. That can understate drawdown and distort intraday risk metrics.

3. Strategy review

The strategy is mathematically coherent, but not strong as a market-making strategy.

Fair price:

In `strategy.py`, the fair value is:

```python
fair = book.mid + cfg.alpha_micro * (book.microprice - book.mid) + cfg.alpha_flow * book.half_spread * trade_imbalance
```

This is coherent. It uses mid, microprice, and past trade imbalance. It is simple, explainable, and appropriate for a take-home.

Microprice:

`book_state.py` implements:

```python
(book.best_ask * book.best_bid_qty + book.best_bid * book.best_ask_qty) / denom
```

That is the standard top-of-book microprice. Good.

Trade imbalance:

`features.py` uses signed trade size over a rolling window:

```python
sign = 1.0 if int(is_maker_ask) == 1 else -1.0
signed / total
```

This is fine. It correctly interprets `is_maker_ask = 1` as buyer-aggressor pressure.

Adaptive spread:

The formula is reasonable:

```python
delta = max(min_half_spread_ticks * tick, spread_mult * half_spread, vol_buffer)
```

But the implementation of `vol_buffer` is weak. `features.volatility_abs()` computes the standard deviation of raw mid differences over an irregular event sequence. Worse, `simulator._update_mark_and_strategy()` calls `features.update_mid()` at every event timestamp, including trade/funding timestamps where the book may not have changed. That means repeated stale mids enter the volatility window and can suppress volatility.

The replacement should be time-normalized and updated only on actual book updates:

```python
dt = (timestamp - last_book_timestamp).total_seconds()
r = (mid - last_mid) / sqrt(max(dt, 1e-6))
sigma_sec = rolling_std(r)
vol_buffer = k_vol * sigma_sec * sqrt(quote_horizon_seconds)
```

Inventory skew:

This is coherent:

```python
reservation = fair - theta_inv * delta * (inventory - q_target) / q_max
```

If long, reservation moves lower. If short, reservation moves higher. Good.

Funding target inventory:

This is coherent but should be framed carefully:

```python
q_target = clip(
    -funding_target_frac * q_max * tanh(funding_rate / funding_scale),
    -q_max / 2,
    q_max / 2,
)
```

Positive funding pushes short, negative funding pushes long. That is fine under the usual convention where positive funding means longs pay shorts. The report should explicitly say the funding sign convention was assumed, not verified from exchange docs.

Adverse-selection filters:

The pressure logic is directionally correct:

```python
pressure = w_book * book.top_imbalance + w_trade * trade_imbalance

bid_delta = delta * (1 + k_adv * max(0, -pressure))
ask_delta = delta * (1 + k_adv * max(0, pressure))
```

Negative pressure widens/stops the bid. Positive pressure widens/stops the ask. Good.

EOD reduce-only behavior:

This is currently flawed. In `strategy.py`:

```python
if is_reduce_only_window(...):
    if account.inventory > 0:
        bid_size = 0.0
    elif account.inventory < 0:
        ask_size = 0.0
```

This disables the inventory-increasing side, but it does not prevent flipping. Example: if inventory is `+0.03 ETH`, ask size could be `0.10 ETH`, which would turn the strategy short if filled. If inventory is flat, both sides can still be quoted and open a new position.

Replace with:

```python
if is_reduce_only_window(timestamp, day_end, self.risk_config.eod_reduce_window_minutes):
    eps = 1e-12

    if account.inventory > eps:
        bid_size = 0.0
        ask_size = min(ask_size, account.inventory)

    elif account.inventory < -eps:
        ask_size = 0.0
        bid_size = min(bid_size, -account.inventory)

    else:
        bid_size = 0.0
        ask_size = 0.0
```

4. Simulator review

The simulator is defensible, but not yet strong.

Event ordering:

`simulator.py` processes each timestamp as:

1. accrue funding from previous timestamp to current timestamp,
2. process trades,
3. process orderbooks,
4. process fundings,
5. update mark and strategy.

This is conservative for fills because trades at timestamp `t` are processed before quotes placed at timestamp `t`. That avoids same-timestamp lookahead.

The test `test_same_timestamp_trade_cannot_fill_new_quote()` covers this. Good.

Latency:

`LiveOrder.is_active()` uses:

```python
timestamp >= active_time
```

Orders are created with:

```python
active_time = timestamp + latency
```

Given the grouped event ordering, this is acceptable. If `latency_ms = 0`, a new quote still cannot fill on already-processed same-timestamp trades. Good.

Order placement/cancellation:

The simulator keeps one bid and one ask. That is appropriate for a baseline.

The big issue is that the strategy cancels/replaces aggressively and loses queue priority. The conservative fill model starts every new order behind visible queue. With a 5-second refresh and frequent BBO movement, the strategy is constantly resetting its queue position. That is probably why the conservative run has only 6 fills.

This is not a simulator bug, but it is a strategy-design weakness. A reviewer will ask: “Why quote at the back of a 50–200 ETH queue with 0.1 ETH size and cancel every few seconds?”

Conservative queue-ahead fill model:

The implementation in `fill_model.py` is simple and defensible:

```python
if conservative_queue and order.queue_ahead > 0:
    consumed_ahead = min(order.queue_ahead, eligible_size)
    order.queue_ahead -= consumed_ahead
    eligible_size -= consumed_ahead
fill_qty = min(order.remaining_quantity, eligible_size)
```

The logic is correct as a conservative approximation. It ignores cancellations ahead, so it underfills. That is acceptable if explicitly stated.

Simple fill sensitivity:

The simple model is useful, but the report wording is wrong. It should not say “optimistic” in a performance sense. It is optimistic about queue priority, but it can produce worse PnL because it exposes the strategy to more toxic fills. The current simple-fill result does exactly that.

Partial fills:

Partial fills are supported. The two fills on order `12873` at the same timestamp show this working. Good.

No-lookahead:

Core no-lookahead is mostly respected. Quotes use already-processed book/funding/trade features, and newly placed quotes cannot fill on prior same-timestamp trades.

However, there is a reporting bug in cancellations.

In `simulator.py`, `_cancel_all()` records cancellation timestamp as:

```python
"timestamp": self.book.timestamp
```

That is wrong when a refresh is triggered by a trade event and no book update exists at the same timestamp. The cancellation is executed at the current simulation timestamp, but the order log can show an older book timestamp. I saw this around fills: cancellation timestamps can appear just before the fill-triggering trade.

Patch:

```python
def _cancel_all(self, reason: str, timestamp: pd.Timestamp | None = None) -> None:
    cancel_ts = timestamp if timestamp is not None else self.book.timestamp
    ...
    "timestamp": cancel_ts
```

Then call:

```python
self._cancel_all("refresh", timestamp)
self._cancel_all("invalid_book", timestamp)
self._cancel_all("quote_crossed_after_book_update", timestamp)
```

5. PnL accounting review

Core accounting is one of the stronger parts.

Cash ledger:

`accounting.py` uses:

```python
self.cash -= signed_qty * fill_price
```

Buy decreases cash, sell increases cash. Correct.

Signed inventory:

`Fill.signed_quantity` is positive for bid fills and negative for ask fills. Correct.

Average-cost realized PnL:

The average-cost logic is correct for adds, partial reductions, full closes, and flips.

For a long reduced by a sell:

```python
realized += close_qty * (fill_price - average_entry_price)
```

For a short reduced by a buy:

```python
realized += close_qty * (average_entry_price - fill_price)
```

Correct.

Unrealized PnL:

The implementation is correct:

```python
long: inventory * (mark - average_entry)
short: abs(inventory) * (average_entry - mark)
```

Fees:

Fee accounting is correct mechanically:

```python
fees_paid += abs(signed_qty) * fill_price * maker_fee_rate
```

But the baseline uses `0.0 bps`. That is acceptable as an assumption, but a serious report needs maker-fee sensitivity. With only `0.055 USD` realized trading PnL in the conservative run, even tiny fees matter.

Funding accrual:

The funding equation is coherent:

```python
delta = -inventory * mark_price * funding_rate * elapsed / period_seconds
```

Positive funding pays shorts and charges longs. Fine if that sign convention is correct. The report should say “assumed.”

Liquidation-adjusted equity:

`liquidation_adjusted_equity()` marks long inventory to bid and short inventory to ask. Correct.

Daily PnL aggregation:

This is a bug.

`metrics.daily_summary()` sets:

```python
"realized_trading_pnl": float(day["realized_trading_pnl"].iloc[-1])
"funding_pnl": float(day["funding_pnl"].iloc[-1])
"fees": float(day["fees"].iloc[-1])
```

Those are cumulative ending values, not daily increments. The daily table therefore misrepresents the PnL decomposition.

Patch concept:

```python
prev_equity = 0.0
prev_realized = 0.0
prev_funding = 0.0
prev_fees = 0.0

for date, day in curve.groupby("date", sort=True):
    end_equity = float(day["equity"].iloc[-1])
    end_realized = float(day["realized_trading_pnl"].iloc[-1])
    end_funding = float(day["funding_pnl"].iloc[-1])
    end_fees = float(day["fees"].iloc[-1])

    daily_realized = end_realized - prev_realized
    daily_funding = end_funding - prev_funding
    daily_fees = end_fees - prev_fees
    daily_pnl = end_equity - prev_equity

    prev_equity = end_equity
    prev_realized = end_realized
    prev_funding = end_funding
    prev_fees = end_fees
```

Also add daily unrealized change:

```python
start_unrealized = previous_day_end_unrealized
end_unrealized = day["unrealized_trading_pnl"].iloc[-1]
daily_unrealized_change = end_unrealized - start_unrealized
```

6. Audit review

The audit is decent but not strong enough for a serious market-data project.

Good checks:

Schema checks exist.

Timestamp ordering exists.

Missing values exist.

Book monotonicity exists.

Negative book quantities exist.

Locked/crossed books exist.

Spread and depth distributions exist.

Trade/book alignment exists.

Funding gap checks exist.

Day-boundary checks exist.

Weak or missing checks:

Exact duplicate row detection is broken. In `data_audit.py`, this is used:

```python
dup_rows = int(df.duplicated().sum())
```

But the loader added `_row_id`, so exact duplicates will not be detected. Fix:

```python
metadata_cols = {"_source_day", "_row_id"}
subset = [c for c in df.columns if c not in metadata_cols]
dup_rows = int(df.duplicated(subset=subset).sum())
```

Trade duplicate timestamps are reported as a warning, but duplicate trade timestamps are not necessarily bad. Multiple executions can share a timestamp. The audit should report count and percentage, and the report should explain that same-timestamp row order is assumed to preserve execution order.

No trade size validation. Add:

```python
trade_size_nonpositive = (trades["size"] <= 0).sum()
```

No trade side validation. Add:

```python
bad_trade_side = ~trades["is_maker_ask"].isin([0, 1])
```

No funding-rate finite/outlier check. Add `np.isfinite()` and robust p99/max checks.

No price outlier check. Add mid jump in ticks:

```python
mid = (ask_price_1 + bid_price_1) / 2
mid_jump_ticks = mid.diff().abs() / tick_size
warn if p99 or max exceeds threshold
```

No trade price outside visible book check. Add whether trade price is outside `[bid_price_20, ask_price_20]` after asof book alignment.

No stale book alignment age. `merge_asof()` does not currently report how old the matched book snapshot is. Add:

```python
book_time = matched orderbook datetime
age_ms = trade_time - book_time
```

Then report p50/p95/max age. If trades are aligned to stale snapshots, fill simulation is much less defensible.

No audit severity for high one-tick spread. The report shows `one_tick_or_less_pct = 80.5%`. That is strategically crucial. If 80% of the market is one tick wide, a maker-only strategy has very little room after fees and queue. This should be highlighted.

7. Metrics and report review

The metrics are directionally useful, but the report undersells the problems.

Good metrics:

Total PnL.

Realized/unrealized/funding split.

Fill count and volume.

Bid versus ask fills.

Inventory stats.

Drawdown.

Sharpe-like 1-minute diagnostic.

Realized spread and toxicity.

Plots for equity, inventory, spread, fills, funding/inventory.

Weaknesses:

The report does not include order count, cancel count, or fill/order ratio. This is essential here because the conservative result has about 18,908 placed orders and only 6 fills.

Add:

```text
placed_orders
cancelled_orders
fill_to_order_ratio
average_quote_lifetime
pct_orders_cancelled_before_active
```

The report does not show audit warning magnitudes. It only lists warning names. It should show:

`trades_duplicate_timestamps = 21,530`

`trade_book_alignment = 579`

`one_tick_or_less_pct = 80.5%`

The simple-fill report incorrectly says the official result uses conservative queue fill. That is a report correctness bug.

The comparison says simple fill is an “optimistic sensitivity.” Better wording:

“Simple fill removes queue-ahead and is optimistic about priority, but it increases exposure to toxic fills. It should be interpreted as an aggressive-fill sensitivity, not a better-performance upper bound.”

Max drawdown is computed from the reported 1-minute equity curve, not necessarily event-level equity. If equity is only sampled once per minute, drawdown can be understated. Either record event-level equity for metrics or maintain event-level drawdown separately.

The Sharpe-like metric over three days is not meaningful and should be labeled as a diagnostic only. The report does this somewhat, but it should be stronger.

8. Test review

The current tests are useful but insufficient.

Existing tests cover:

Long/short accounting.

Fees.

Funding.

Mark-to-market.

Simple fill partials.

Queue-ahead consumption.

Wrong-side fill prevention.

Same-timestamp no-fill.

Inventory clipping.

Daily aggregation.

Invalid crossed book.

Missing tests a serious reviewer would expect:

Tick rounding test. This would currently fail:

```python
assert floor_to_tick(100.3, 0.1) == pytest.approx(100.3)
assert ceil_to_tick(100.1, 0.1) == pytest.approx(100.1)
```

Current behavior can round down one tick due binary float error.

Spread tick comparison test. A one-tick spread like `0.09999999999990905` should not be classified as less than one tick if the intended spread is one tick.

EOD reduce-only no-flip test. Example: inventory `+0.03`, ask size must be at most `0.03`; inventory `0`, both sides must be disabled.

Daily PnL decomposition test. Current test checks only `daily_pnl`, not daily realized/funding/fees increments.

Report fill-model text test. Simple fill report should say `simple`, not conservative.

Order cancellation timestamp test. If a fill at trade timestamp triggers refresh, cancellation timestamp should equal the trade timestamp, not stale book timestamp.

No quote when trade/book alignment stale or bad-data state active.

Audit duplicate row test excluding `_row_id`.

Trade side validation test: `is_maker_ask` must be only `0` or `1`.

Negative or zero trade size test.

Liquidation-adjusted equity test for both long and short.

Event-level drawdown test: a large intra-minute drawdown should be captured.

Queue model deeper-level test: if bid order is below best bid, queue ahead should include all visible better bids and equal price.

Funding convention test with changing funding rate over intervals.

9. Code-quality review

Architecture:

Good. The separation of concerns is clean: data loading, audit, book state, features, strategy, fill model, accounting, risk, simulator, metrics, reporting. This is a strong point.

Performance:

The simulator uses prepared NumPy arrays instead of iterating DataFrames row by row. Good. But full event-level metrics may increase output size; solve by keeping event-level risk metrics internally and writing resampled equity for plots.

Reproducibility:

Good but incomplete. There is a `pyproject.toml`, config file, CLI, and generated reports. Add a copied config snapshot into each report directory:

```text
reports/baseline/config_used.yaml
```

Also include git commit hash if available.

CLI usability:

Good enough. `mm-backtest audit`, `run`, and `--fill-model` are clean.

Config quality:

Good baseline parameters, but some fields are unused: `requote_delta_ticks`, `funding_retarget_threshold`. Either implement them or remove them.

Typing/dataclasses:

Generally good. `_PreparedArrays` uses `object` types; acceptable for a take-home, but typed NumPy arrays would be cleaner.

Separation of concerns:

Mostly good. One issue: `_cancel_all()` depends on `self.book.timestamp` rather than the simulator event timestamp. That is a simulator-state leak into reporting.

Generated reports:

It is acceptable to include generated reports, but the report must be reproducible and truthful. The hard-coded fill-model assumption is the main issue.

10. Top 10 issues ranked by severity

11. **Daily PnL decomposition is misleading**
    File: `src/market_maker/metrics.py`, `daily_summary()`
    Severity: high.
    Daily realized/funding/fees are cumulative end-of-day values, not daily increments. This is a report correctness problem.

12. **Float tick rounding can move quotes by one tick**
    File: `src/market_maker/strategy.py`, `floor_to_tick()` / `ceil_to_tick()`
    Severity: high.
    Example: `floor_to_tick(100.3, 0.1)` returns `100.2` under normal binary float behavior. This can materially alter quotes.

13. **EOD reduce-only can open or flip inventory**
    File: `src/market_maker/strategy.py`, EOD block
    Severity: high.
    Current logic disables one side but does not cap reduce-side quantity to current inventory and does not stop flat accounts from opening new positions.

14. **Conservative baseline has only 6 fills**
    Files: `reports/baseline/summary.csv`, `reports/baseline/fills.csv`
    Severity: high for interpretation.
    Six fills over three days is not enough evidence of market-making quality.

15. **Positive baseline PnL is mostly inventory drift**
    File: `reports/baseline/final_report.md`
    Severity: high for strategy credibility.
    `12.66 / 12.82 USD` is unrealized trading PnL. The report acknowledges this, which is good, but the submission must not frame this as a successful market maker.

16. **Simple-fill sensitivity is negative and shows adverse selection**
    File: `reports/simple_fill/final_report.md`
    Severity: high for model credibility.
    With 85 fills, realized trading PnL is about `-9.83 USD`. That suggests the quotes are toxic when they actually trade.

17. **Report hard-codes conservative fill model**
    File: `src/market_maker/reporting.py`, `build_markdown_report()`
    Severity: medium-high.
    `reports/simple_fill/final_report.md` incorrectly says the official result uses conservative queue-ahead. This looks sloppy.

18. **Audit duplicate-row check is broken by `_row_id`**
    File: `src/market_maker/data_audit.py`
    Severity: medium-high.
    `df.duplicated()` includes `_row_id`, so exact duplicate market rows are not detected.

19. **Metrics drawdown is based on 1-minute sampled equity**
    File: `src/market_maker/metrics.py`, `summarize_metrics()`
    Severity: medium-high.
    Max drawdown and Sharpe-like statistics should be computed from event-level equity or an explicitly maintained event-level risk series.

20. **Volatility model is not time-normalized and uses repeated stale mids**
    Files: `src/market_maker/features.py`, `src/market_maker/simulator.py`
    Severity: medium.
    This weakens adaptive spread and jump/cooldown behavior.

21. Most likely interviewer criticisms

A quant interviewer will probably say:

“You have a positive result only because you ended short into a down move. Where is the realized spread capture?”

“Six fills in three days is not a backtest. It is a toy execution trace.”

“Why does the simple fill model lose money if your market-making logic is good?”

“Your conservative fill model is so conservative that it avoids most adverse selection. Are you underfilling your bad trades?”

“Why are you canceling every few seconds if your queue model puts you at the back every time?”

“Why is 80% of the market one tick wide, and how can your strategy make money after fees?”

“Why are fees zero? What happens at +1 bps or +2 bps?”

“Why are daily realized PnL values cumulative?”

“Why does the simple-fill report say conservative fill?”

“Did you verify the funding sign convention?”

“Can your tick rounding move a quote by one tick?”

12. What to fix before submission

If you only have 2 hours:

Fix these and submit with caveats.

1. Fix tick rounding in `strategy.py`.

```python
def floor_to_tick(price: float, tick: float) -> float:
    n = floor(price / tick + 1e-9)
    return round(n * tick, 10)

def ceil_to_tick(price: float, tick: float) -> float:
    n = ceil(price / tick - 1e-9)
    return round(n * tick, 10)
```

Better long-term: convert all prices to integer ticks internally.

2. Fix spread tick comparison:

```python
spread_ticks = int(round(book.spread / self.tick_size))
if spread_ticks < self.risk_config.min_economic_spread_ticks:
    return self._empty("uneconomic_spread")
```

3. Fix EOD reduce-only:

```python
if is_reduce_only_window(timestamp, day_end, self.risk_config.eod_reduce_window_minutes):
    eps = 1e-12
    if account.inventory > eps:
        bid_size = 0.0
        ask_size = min(ask_size, account.inventory)
    elif account.inventory < -eps:
        ask_size = 0.0
        bid_size = min(bid_size, -account.inventory)
    else:
        bid_size = 0.0
        ask_size = 0.0
```

4. Fix daily PnL decomposition in `metrics.py`.

5. Fix report text to use `config.execution.fill_model`.

```python
f"- Fill model: `{config.execution.fill_model}`."
```

6. Add a paragraph to the report:

“This is a simulator-validation baseline, not evidence of robust market-making edge. Conservative fills are too sparse, and simple fills show adverse selection.”

7. Add maker fee sensitivity table manually or via one extra run if possible.

8. Add order count and fill/order ratio to metrics/report.

If you have 1 day:

Do the 2-hour fixes, plus:

Compute event-level drawdown internally.

Add audit checks for trade side, trade size, duplicate rows excluding metadata, stale book age, trade price outside visible L2, mid jump outliers, and funding outliers.

Add tests for tick rounding, EOD reduce-only no-flip, daily decomposition, hard-coded report fill model, duplicate audit, and cancellation timestamp.

Improve report: show warning counts, spread stats, one-tick percentage, fill model comparison, fee sensitivity, and conclusion framing.

Add terminal liquidation as an explicit scenario, not only a single metric.

If you have 3 days:

Do all above, plus improve the strategy:

Stop canceling/replacing every side blindly.

Keep orders if desired price has not moved materially, to preserve queue.

Quote inside the spread when spread is wide enough and fair value supports it.

Add queue-ahead threshold: avoid joining huge queues unless the quote is intentionally passive.

Add a parameter sensitivity grid: spread multiplier, refresh interval, inventory skew, no funding, fee bps.

Calibrate fills against visible book changes: a queue model that uses both trades and same-side depth reductions would be more reviewer-friendly.

Add realized spread by side and by fill model.

Add “flat PnL after terminal unwind” as the headline, with mark-to-mid as secondary.

13. How to frame the result

Do **not** frame this as a successful market maker.

Correct framing:

“This is a conservative, event-driven simulator-validation baseline. The simulator, accounting, and diagnostics are the main contribution. The strategy itself is intentionally simple and not proven profitable. The conservative queue model produces too few fills for statistical confidence, while the simple fill model reveals adverse selection. The positive baseline PnL is mainly residual short inventory marked favorably, not robust spread capture.”

That framing is honest and defensible.

Bad framing:

“The strategy made +12.82 USD, so the market maker works.”

That will fail under questioning.

14. Are the current results suspicious?

Yes, but not necessarily fraudulent or broken.

Only 6 conservative fills:

Suspicious as evidence. It means the conservative queue model plus quote/cancel behavior makes the bot barely trade. This is not enough to validate edge.

Positive conservative result mostly unrealized:

Suspicious as a market-making result. It is probably a lucky directional short into a price decline.

Simple fill negative:

This is actually useful. It says that when fills are easier to obtain, the strategy gets adversely selected. That is exactly the kind of diagnostic a good report should discuss.

Trade/book alignment warning:

This matters. The fill model depends on trade price and side relative to the book. If 579 trades do not align with the BBO within tolerance, the report should quantify percentage and explain whether those trades were excluded, tolerated, or considered timestamp noise.

Conservative positive but simple negative:

This does not prove the conservative model is better. It may mean the conservative model filters out many toxic fills by construction. That is defensible as a lower-fill model, but not evidence of edge.

15. Highest-impact improvements

The highest-impact changes are:

First, fix correctness and reporting: tick rounding, daily decomposition, EOD reduce-only, hard-coded report text, duplicate audit, event-level drawdown.

Second, change quote behavior. The current strategy repeatedly joins queues and resets queue priority. That is structurally bad under the conservative model. Add queue-aware quote preservation.

Third, add fee sensitivity. With one-tick spreads and tiny realized PnL, fees are existential.

Fourth, add terminal flattening and report flat PnL. Residual inventory dominates the result.

Fifth, improve fill calibration. Conservative queue-ahead is defensible, but too sparse. Add a middle model that uses visible book depletion:

For a bid order at price `p`, maintain queue ahead. On each orderbook update, estimate displayed same-side depth ahead:

```text
new_visible_ahead = sum(bid_qty_i where bid_price_i >= p)
queue_ahead = min(queue_ahead, new_visible_ahead)
```

Then trades consume queue ahead as currently implemented. This allows cancellations ahead to reduce queue without assuming immediate priority.

This is more realistic than the current conservative model and less optimistic than simple fill.

16. Proposed code changes for weak parts

Tick-safe price handling in `strategy.py`:

```python
def price_decimals_from_tick(tick: float) -> int:
    text = f"{tick:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".")[1])

def floor_to_tick(price: float, tick: float) -> float:
    decimals = price_decimals_from_tick(tick)
    n = floor(price / tick + 1e-9)
    return round(n * tick, decimals)

def ceil_to_tick(price: float, tick: float) -> float:
    decimals = price_decimals_from_tick(tick)
    n = ceil(price / tick - 1e-9)
    return round(n * tick, decimals)
```

Daily metric fix in `metrics.py`:

```python
previous_end_equity = 0.0
previous_realized = 0.0
previous_unrealized = 0.0
previous_funding = 0.0
previous_fees = 0.0

for date, day in curve.groupby("date", sort=True):
    end_equity = float(day["equity"].iloc[-1])
    end_realized = float(day["realized_trading_pnl"].iloc[-1])
    end_unrealized = float(day["unrealized_trading_pnl"].iloc[-1])
    end_funding = float(day["funding_pnl"].iloc[-1])
    end_fees = float(day["fees"].iloc[-1])

    rows.append({
        "date": date,
        "starting_equity": previous_end_equity,
        "ending_equity": end_equity,
        "daily_pnl": end_equity - previous_end_equity,
        "daily_realized_trading_pnl": end_realized - previous_realized,
        "daily_unrealized_trading_pnl_change": end_unrealized - previous_unrealized,
        "daily_funding_pnl": end_funding - previous_funding,
        "daily_fees": end_fees - previous_fees,
        ...
    })

    previous_end_equity = end_equity
    previous_realized = end_realized
    previous_unrealized = end_unrealized
    previous_funding = end_funding
    previous_fees = end_fees
```

Report fill-model fix in `reporting.py`:

```python
fill_model_label = config.execution.fill_model
lines = [
    ...
    f"- Fill model: `{fill_model_label}`.",
    ...
]
```

Order cancellation timestamp fix in `simulator.py`:

```python
def _cancel_all(self, reason: str, timestamp: pd.Timestamp | None = None) -> None:
    cancel_ts = timestamp if timestamp is not None else self.book.timestamp
    for side, order in list(self.active_orders.items()):
        if order is not None and order.status == "live":
            order.status = "cancelled"
            self.order_rows.append({
                "timestamp": cancel_ts,
                ...
                "reason": reason,
            })
        self.active_orders[side] = None
```

Audit duplicate fix in `data_audit.py`:

```python
metadata_cols = {"_source_day", "_row_id"}
market_cols = [c for c in df.columns if c not in metadata_cols]
dup_rows = int(df.duplicated(subset=market_cols).sum())
```

Audit trade validity additions:

```python
bad_trade_size = int((data.trades["size"].astype(float) <= 0).sum())
bad_trade_side = int((~data.trades["is_maker_ask"].isin([0, 1])).sum())

_add(rows, "trades_nonpositive_size", "error" if bad_trade_size else "ok", bad_trade_size, "size <= 0")
_add(rows, "trades_bad_side", "error" if bad_trade_side else "ok", bad_trade_side, "is_maker_ask not in {0,1}")
```

True reduce-only patch in `strategy.py`:

```python
if is_reduce_only_window(timestamp, day_end, self.risk_config.eod_reduce_window_minutes):
    eps = 1e-12
    if account.inventory > eps:
        bid_size = 0.0
        ask_size = min(ask_size, account.inventory)
    elif account.inventory < -eps:
        ask_size = 0.0
        bid_size = min(bid_size, -account.inventory)
    else:
        bid_size = 0.0
        ask_size = 0.0
```

Queue-aware quote preservation idea in `simulator.py`:

Instead of canceling both sides on every refresh:

```python
for side in [BID, ASK]:
    existing = active_orders[side]
    desired = desired_order[side]

    if desired is None:
        cancel existing
        continue

    if existing is live and abs(existing.price - desired.price) <= keep_existing_ticks * tick:
        keep existing to preserve queue priority
        optionally resize downward only
    else:
        cancel existing
        place desired
```

This would directly address the “six fills in three days” problem.

17. Reviewer-risk section

The project could look bad if you claim profitability. The right reviewer will immediately see that the conservative result is driven by residual inventory. The report must make that impossible to miss.

The project could also look bad if the reviewer notices the simple-fill report says conservative fill. That is an avoidable credibility hit.

The daily PnL table could create an uncomfortable interview moment because the realized/funding columns are cumulative. Fix this before submission.

The float tick bug is the kind of issue trading engineers care about. Tick rounding must be robust.

The six-fill baseline makes the strategy statistically meaningless. You can defend the simulator, but not the trading edge.

18. Defense script

A good way to explain it in an interview:

“I treated this primarily as a simulator and market-microstructure exercise, not as an overfit alpha search over three days. The official result uses conservative queue-ahead fills because L2 snapshots and prints do not reveal true queue position. That model probably underfills, but it avoids pretending we are first in queue. I also included a simple-fill sensitivity, which produces more fills and worse realized PnL; that is useful because it shows adverse selection. The positive conservative PnL is mostly terminal inventory mark-to-market, so I do not claim the strategy has robust market-making edge. The main value of the project is the event-driven simulator, accounting decomposition, fill-model comparison, and diagnostics. If I extended it, I would improve queue calibration using book depletion, preserve queue priority by reducing cancel churn, add maker-fee sensitivity, and force terminal flattening.”

That is a strong, honest defense.

19. Final submission checklist

Before submitting:

Fix tick rounding.

Fix EOD reduce-only so it cannot open or flip.

Fix daily PnL decomposition.

Fix report fill-model text.

Fix duplicate-row audit excluding `_row_id`.

Add trade side and nonpositive trade size audit checks.

Add event-level drawdown or clearly label sampled drawdown.

Add order count, cancel count, and fill/order ratio to the report.

Add fee sensitivity: at least `0 bps`, `1 bps`, `2 bps`.

Add a clear headline: “simulator-validation baseline, not proven profitable MM.”

Add tests for all patched issues.

Regenerate baseline and simple-fill reports.

Update fill-model comparison wording.

Include config snapshot in each report directory.

Run:

```bash
pytest
mm-backtest run --output-dir reports/baseline
mm-backtest run --fill-model simple --output-dir reports/simple_fill
```

Then submit.

Final recommendation:

Do **not** submit the current version unchanged. Fix the small correctness/reporting issues first. Then submit it as a **strong simulator and honest baseline**, not as a profitable market-making bot.
