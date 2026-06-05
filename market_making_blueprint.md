1. Problem Boundary

Facts from the take-home: the task is to design a market-making bot and backtest it on three calendar days, 2026-03-19 to 2026-03-21, for a single ETH perpetual market around 2200 USD. The repo describes three data streams: 20-level L2 orderbook snapshots, trades with `is_maker_ask`, and funding rates approximately every 20 seconds. ([GitHub][1])

Assumptions to make explicit before coding:

The strategy is maker-only by default. It places passive limit orders only. It never crosses the spread during normal operation. Any taker liquidation is optional and should be reported separately as a “terminal liquidation-adjusted PnL” sensitivity, not mixed into the baseline.

The instrument is modeled as a linear ETH perpetual contract with inventory measured in ETH and PnL measured in USD/USDT. No inverse contract mechanics are assumed.

Initial inventory is 0 ETH. Initial cash is 0 USD. Cash can be negative because this is a backtest accounting ledger, not a margin wallet.

Fees are not specified in the repo, so the baseline should use `maker_fee_bps = 0.0`, with sensitivity at `-1.0 bps`, `0.0 bps`, and `+2.0 bps`. The final report must clearly say whether PnL is before or after fees.

Tick size is not assumed. It must be inferred from observed prices during the data audit. Use the smallest stable positive increment in best bid, best ask, and trade prices after rounding-noise filtering. If the inferred tick is unstable, choose the modal price increment and document it.

Order size is fixed per side in the baseline, for example `base_order_size_eth = 0.10`, then clipped by inventory limits. No iceberg, hidden quantity, or multiple levels are modeled in the baseline.

Latency is modeled conservatively. An order submitted at time `t` becomes eligible for fills only strictly after `t`, either after `latency_ms` or after the next market event, whichever is later. Baseline recommendation: `latency_ms = 250 ms` if timestamps have enough resolution; otherwise “next event only.” This avoids same-timestamp lookahead.

Queue position cannot be known because there are snapshots and trades but no order IDs, order acknowledgements, cancellations, or full order-level queue. Therefore queue is simulated. The recommended model is conservative queue priority: when placing at an existing visible price level, our order sits behind displayed quantity at that price and all better prices that must be consumed first.

Funding payment timing is not specified by the described files. The safe assumption is continuous accrual using the latest known funding rate, with a configurable `funding_period_hours = 8`. If the data audit shows the funding rate is already interval-normalized, change the normalization and state it. Positive funding is assumed to mean longs pay shorts, which is the common linear perp convention; this must be verified if the doc clarifies otherwise.

Leverage, margin liquidation, collateral interest, bankruptcy price, ADL, and exchange risk engine behavior are out of scope. The backtest reports inventory and drawdown limits but does not simulate forced liquidation.

The model will not simulate hidden liquidity, real exchange matching engine priority, cancels by other participants, order acknowledgement failure, websocket packet loss, rate limits, maker rebates unless configured, or multi-venue hedging.

The backtest should run continuously across the three days, carrying inventory across day boundaries. Daily PnL is computed from mark-to-market equity differences at UTC day boundaries. The end-of-period inventory is marked to mid in the baseline, with an optional conservative liquidation check at bid for long inventory and ask for short inventory.

2. Data Audit Plan

The audit must run before strategy development. No strategy result is trustworthy until the audit passes or the failure handling rules are documented.

Timestamp ordering. For each file, convert `datetime` to a single timezone-aware or timezone-naive UTC convention, preserving nanosecond precision if available. Verify non-decreasing order within each daily file and after concatenating all days. Failure implies the event loop could process future information before past information. If only small local disorder exists, stable-sort by timestamp and original row index; if large disorder exists, report it and avoid using affected intervals.

Schema completeness. For orderbook files, require `datetime`, `bid_price_i`, `bid_qty_i`, `ask_price_i`, `ask_qty_i` for levels 1 through 20. For trades, require `datetime`, `price`, `size`, `is_maker_ask`. For funding, require `datetime`, `funding_rate`. These column names match the repo description. ([GitHub][1]) Missing columns mean the simulator cannot run without changing assumptions.

Missing values. Check nulls in all price, quantity, trade, side, and funding fields. Null best bid/ask means no quoting. Null deeper levels weaken the queue model. Null trade price/size/side means the trade cannot be used for fills. Null funding means carry forward the last valid funding rate only up to a maximum staleness threshold.

Orderbook monotonicity. For every snapshot, require bid prices to be strictly decreasing or non-increasing by level and ask prices strictly increasing or non-decreasing by level. Quantities must be non-negative. Failure means cumulative depth and queue-ahead estimates are invalid. Bad snapshots should be dropped or flagged as “no quote” intervals.

Crossed or locked books. Check `bid_price_1 < ask_price_1`. Locked book means zero spread; crossed book means negative spread. Failure implies mid price and passive quote placement are invalid. The strategy should stop quoting on crossed books and optionally skip locked books unless a clear tick-size convention allows safe quotes.

Spread distribution. Compute spread in USD, spread in ticks, median, p5, p50, p95, p99, maximum, and percentage of one-tick/zero/negative spreads. Failure matters because a market-making strategy cannot earn edge if the spread is usually too narrow relative to fees and adverse selection.

Depth distribution. Compute quantity and notional depth at top 1, 5, 10, and 20 levels on each side. Also compute imbalance. Failure matters because order size and queue fill assumptions depend on visible depth. If `base_order_size_eth` is larger than top-of-book depth, the fill model becomes unrealistic.

Trade/orderbook alignment. For each trade, align to the most recent orderbook snapshot at or before the trade timestamp. If `is_maker_ask = 1`, the aggressor is a buyer, so the trade should generally occur at or above the contemporaneous best ask. If `is_maker_ask = 0`, the aggressor is a seller, so the trade should generally occur at or below the contemporaneous best bid. Small mismatches can be due to sampling; large or frequent mismatches imply snapshots are too sparse or timestamps are not directly comparable, and the fill model must become more conservative.

Funding timestamp alignment. Check funding coverage over the full period, interval distribution, gaps, duplicates, and whether funding starts before the first orderbook snapshot. Since funding is described as approximately every 20 seconds, large gaps imply stale funding state and should disable funding-based quoting until a fresh value arrives. ([GitHub][1])

Duplicate snapshots. Check exact duplicate rows and duplicate timestamps. Duplicate snapshots can be harmless but should be compressed for efficiency if identical. Conflicting snapshots with the same timestamp require deterministic event ordering and may imply exchange batch updates.

Duplicate trades. Check exact duplicate trade rows. Because there is no trade ID in the described schema, do not automatically drop exact duplicates unless the audit strongly suggests repeated file rows. Dropping real repeated prints would understate fills; keeping duplicated data would overstate fills. The report should state the chosen rule.

Outlier prices. Check mid-price jumps, trade-price jumps, trades outside the visible 20-level book, and prices far from rolling median. Extreme outliers can create fake fills and fake PnL. Outliers should either stop quoting for a cooldown window or be excluded only with a documented threshold.

Outlier sizes. Check trade size and book quantities using robust percentiles. Very large trades are important and should not be dropped by default, but they can dominate fill simulation. If large trades exceed visible 20-level depth, the simulator should not assume all hidden depth was available to our quote.

Day-boundary handling. Verify that each daily file covers only its date, whether there are overlaps or gaps between 2026-03-19, 2026-03-20, and 2026-03-21, and whether the last book of one day should seed the first state of the next. Failure changes daily PnL attribution and may create artificial inventory jumps.

3. Mathematical Definitions

Let `B_t = bid_price_1`, `A_t = ask_price_1`, `b_t = bid_qty_1`, and `a_t = ask_qty_1`.

Mid price:

`M_t = (B_t + A_t) / 2`

Microprice:

`μ_t = (A_t * b_t + B_t * a_t) / (a_t + b_t)`

This moves closer to the ask when bid depth is larger than ask depth, reflecting upward short-term pressure.

Spread:

`s_t = A_t - B_t`

Half-spread:

`h_t = s_t / 2`

Spread in basis points:

`s_bps,t = 10,000 * s_t / M_t`

Inventory in ETH:

`q_t = current signed ETH position`

Positive `q_t` means long ETH perp. Negative `q_t` means short ETH perp.

Cash ledger:

For a fill of signed quantity `Δq_i` at price `p_i`, where buy is positive and sell is negative:

`C_i = C_{i-1} - Δq_i * p_i`

A buy decreases cash. A sell increases cash.

Fee ledger:

`Fee_i = Fee_{i-1} + maker_fee_rate * |Δq_i| * p_i`

where `maker_fee_rate = maker_fee_bps / 10,000`.

Funding PnL, continuous accrual assumption:

Between timestamps `t_{k-1}` and `t_k`, with latest known funding rate `r_{k-1}` and mark `M_{k-1}`:

`ΔF_k = - q_{k-1} * M_{k-1} * r_{k-1} * (Δt_k / T_f)`

where `T_f = funding_period_hours * 3600`.

If `r > 0`, longs pay and shorts receive.

Mark-to-market equity:

`E_t = C_t + q_t * M_t + F_t - Fee_t`

Total PnL from start:

`PnL_total,t = E_t - E_0`

Since `E_0 = 0` under the baseline, `PnL_total,t = E_t`.

Realized trading PnL should be lot-based or average-cost based. With average cost `p_avg`, if an incoming fill reduces an existing position:

For long inventory reduced by a sell:

`Realized += close_qty * (p_fill - p_avg)`

For short inventory reduced by a buy:

`Realized += close_qty * (p_avg - p_fill)`

Unrealized trading PnL:

If `q_t > 0`:

`Unrealized_t = q_t * (M_t - p_avg)`

If `q_t < 0`:

`Unrealized_t = |q_t| * (p_avg - M_t)`

If `q_t = 0`:

`Unrealized_t = 0`

PnL decomposition:

`PnL_total,t = Realized_trading_t + Unrealized_trading_t + Funding_t - Fees_t`

Drawdown:

`Peak_t = max_{u ≤ t} E_u`

`DD_t = E_t - Peak_t`

`MaxDD = min_t DD_t`

For reporting as a positive loss number:

`MaxDrawdownLoss = -min_t DD_t`

Sharpe-like intraday metric:

Use fixed-time resampled equity, preferably 1-minute marks:

`ΔE_j = E_{minute_j} - E_{minute_{j-1}}`

`Sharpe_1m_dailyized = sqrt(1440) * mean(ΔE_j) / std(ΔE_j)`

This is not a statistically reliable Sharpe over only three days. It is a stability diagnostic, not proof of profitability.

Inventory risk penalty:

`Penalty_t = λ_q * (q_t / q_max)^2`

or in price-skew form:

`skew_px_t = θ_inv * δ_t * (q_t - q_target_t) / q_max`

where `δ_t` is the base half-quote distance, `θ_inv` is the inventory-skew strength, and `q_target_t` is the funding-adjusted target inventory.

4. Strategy Design

Recommended baseline: single-level, maker-only, inventory-skewed market maker using mid/microprice fair value, adaptive spread, funding target inventory, and adverse-selection filters.

Fair price model:

Compute top-of-book imbalance:

`I_book,t = (b_t - a_t) / (b_t + a_t)`

Compute trade imbalance using only past trades:

For trade `j`, define:

`sign_j = +1` if `is_maker_ask = 1`

`sign_j = -1` if `is_maker_ask = 0`

Then over an EWMA or rolling window:

`I_trade,t = Σ sign_j * size_j * w_j / Σ size_j * w_j`

with `I_trade,t ∈ [-1, 1]`.

Fair price:

`fair_t = M_t + α_micro * (μ_t - M_t) + α_flow * h_t * I_trade,t`

Baseline parameters:

`α_micro = 0.5`

`α_flow = 0.25`

This keeps the model simple and explainable. It does not train on three days, avoiding overfit.

Funding target inventory:

Let `r_t` be the latest known funding rate. Define:

`z_fund,t = tanh(r_t / funding_scale)`

`q_target_t = clip(- funding_target_frac * q_max * z_fund,t, -q_max/2, q_max/2)`

Positive funding pushes target inventory short. Negative funding pushes target inventory long.

Baseline:

`funding_scale = 1e-4`, assuming rates are decimals per funding period, to be verified.

`funding_target_frac = 0.25`

Reservation price:

`reservation_t = fair_t - θ_inv * δ_t * (q_t - q_target_t) / q_max`

If inventory is too long, reservation price decreases, making the ask easier to hit and the bid less attractive. If inventory is too short, reservation price increases.

Volatility estimate:

Use rolling absolute mid-price changes over a past-only window:

`σ_abs,t = std(M_u - M_{u-1})` over the last `W_vol` seconds.

Convert to expected movement over quote horizon `τ_quote`:

`vol_buffer_t = k_vol * σ_abs,t * sqrt(τ_quote / Δt_ref)`

If using time-normalized volatility, use:

`σ_sec,t = std(ΔM_u / sqrt(Δt_u))`

`vol_buffer_t = k_vol * σ_sec,t * sqrt(τ_quote)`

Base quote half-distance:

`δ_t = max(min_half_spread_ticks * tick, spread_mult * h_t, vol_buffer_t)`

Baseline:

`min_half_spread_ticks = 2`

`spread_mult = 1.0`

`W_vol = 60 seconds`

`τ_quote = 5 seconds`

`k_vol = 1.0`

Adverse-selection pressure:

`pressure_t = w_book * I_book,t + w_trade * I_trade,t`

Baseline:

`w_book = 0.5`

`w_trade = 0.5`

Side-specific widening:

`δ_bid,t = δ_t * (1 + k_adv * max(0, -pressure_t))`

`δ_ask,t = δ_t * (1 + k_adv * max(0, pressure_t))`

If pressure is strongly downward, widen the bid. If pressure is strongly upward, widen the ask.

Baseline:

`k_adv = 0.5`

Raw quote prices:

`raw_bid_t = reservation_t - δ_bid,t`

`raw_ask_t = reservation_t + δ_ask,t`

Passive price constraints:

`bid_px_t = min(floor_to_tick(raw_bid_t), A_t - tick)`

`ask_px_t = max(ceil_to_tick(raw_ask_t), B_t + tick)`

Optional additional constraint for reviewer-friendly conservatism:

Do not quote more aggressively than one tick inside the current spread unless the spread is at least four ticks wide.

Inventory-aware order sizes:

Let:

`x_t = (q_t - q_target_t) / q_max`

Then:

`bid_size_raw = base_order_size_eth * clip(1 - x_t, 0, 2)`

`ask_size_raw = base_order_size_eth * clip(1 + x_t, 0, 2)`

Apply hard inventory clipping:

`bid_size_t = min(bid_size_raw, q_max - q_t)`

`ask_size_t = min(ask_size_raw, q_max + q_t)`

If `q_t >= q_max`, bid size is zero. If `q_t <= -q_max`, ask size is zero.

Baseline:

`base_order_size_eth = 0.10`

`q_max = 1.00 ETH`

Quote refresh and cancellation logic:

Maintain at most one live bid and one live ask.

Cancel and replace when any of the following is true:

Current quote would cross after a book update.

Quote age exceeds `max_quote_age_seconds`.

Time since last refresh exceeds `refresh_interval_seconds`.

Best bid or best ask moves by at least `requote_bbo_ticks`.

Inventory changes due to a fill.

Volatility regime changes enough that `δ_t` changes by more than `requote_delta_ticks`.

Funding target changes enough that `|q_target_new - q_target_old| > funding_retarget_threshold`.

Baseline:

`refresh_interval_seconds = 5`

`max_quote_age_seconds = 10`

`requote_bbo_ticks = 1`

`requote_delta_ticks = 2`

Adverse-selection no-quote filters:

Stop quoting both sides if the book is crossed, locked, has missing best bid/ask, or spread is below minimum economic spread.

Stop quoting the vulnerable side if recent pressure is extreme:

If `pressure_t > pressure_stop`, disable ask.

If `pressure_t < -pressure_stop`, disable bid.

Baseline:

`pressure_stop = 0.85`

Volatility/spread regime adaptation:

If rolling volatility exceeds its rolling 95th percentile or if a single mid-price jump exceeds `jump_ticks_stop`, cancel quotes and enter cooldown.

Baseline:

`jump_ticks_stop = 10`

`cooldown_seconds = 10`

Essential design choice: keep this strategy explainable. A take-home reviewer will prefer a robust, well-accounted baseline over a fragile predictive model trained on three days.

5. Fill Simulation Model

The fill simulator must use only information available at or before the event being processed. It must not fill orders placed after seeing the same trade.

Trade direction usage:

`is_maker_ask = 1` means the aggressor buyer hit resting asks. Therefore only our resting ask can be filled.

`is_maker_ask = 0` means the aggressor seller hit resting bids. Therefore only our resting bid can be filled.

A resting ask at price `p_ask` is potentially filled by a trade if:

`is_maker_ask = 1`

`trade_price >= p_ask`

`trade_time >= order_active_time`

A resting bid at price `p_bid` is potentially filled by a trade if:

`is_maker_ask = 0`

`trade_price <= p_bid`

`trade_time >= order_active_time`

Execution price should be our resting limit price, not necessarily the observed trade price:

`fill_price = order_limit_price`

This is correct for a maker limit order if an aggressor reaches our level.

Partial fills:

Each order has `remaining_qty`. A qualifying trade can fill:

`fill_qty = min(order_remaining_qty, eligible_trade_qty_after_queue)`

After a partial fill, the order remains live with reduced quantity unless the strategy cancels it later.

A. Simple baseline fill model

Assumption: our order has immediate queue priority once resting.

For an ask:

If a buy-aggressor trade has `trade_price >= ask_px`, fill:

`min(ask_remaining, trade_size)`

For a bid:

If a sell-aggressor trade has `trade_price <= bid_px`, fill:

`min(bid_remaining, trade_size)`

Pros: easy to implement, easy to debug, good first integration test.

Cons: optimistic. It ignores displayed queue ahead of us. It can overstate fills, especially when quoting at the best bid or best ask.

B. Conservative reviewer-friendly fill model

Assumption: if we post at a visible existing price level, we are behind all displayed quantity at that price and all better prices that must trade before us. We do not get queue improvement from cancels because cancels are not observed.

At order placement, using the latest known orderbook snapshot:

For a bid order at price `p`:

`ahead_qty = Σ bid_qty_i for all bid_price_i >= p`

For an ask order at price `p`:

`ahead_qty = Σ ask_qty_i for all ask_price_i <= p`

If the quote improves the book inside the spread, `ahead_qty = 0`, because there is no visible existing queue at that price.

For every qualifying trade:

First consume queue ahead:

`consume_ahead = min(ahead_qty, trade_size)`

`ahead_qty -= consume_ahead`

`remaining_trade_size = trade_size - consume_ahead`

Then fill our order:

`fill_qty = min(order_remaining_qty, remaining_trade_size)`

Important nuance: use only same-side aggressive trades that reach our price. For asks, only `is_maker_ask = 1` trades with `trade_price >= ask_px`. For bids, only `is_maker_ask = 0` trades with `trade_price <= bid_px`.

Pros: much more defensible. It avoids pretending we are first in queue at top of book.

Cons: conservative because it ignores cancellations ahead of us. It may under-fill quotes that would have advanced in queue in real life.

Recommended model:

Use model B as the main reported result. Implement model A only as a sanity check and upper-bound sensitivity. A strong report can show: “optimistic fills produce X; conservative queue fills produce Y; all conclusions use conservative queue fills.”

Avoiding lookahead bias:

Orders created after processing an orderbook snapshot at time `t` cannot be filled by trades at time `t`.

A quote uses the latest book and funding known after processing market events up to time `t`, but is active only at `t + latency`.

Funding signal uses last known funding value, never future funding rows.

Volatility, trade imbalance, and adverse-selection features use only historical data up to the current timestamp.

6. Backtest Event Loop

Run the simulation in chronological order across all three days.

Daily load:

Load `orderbook/YYYY-MM-DD.parquet`, `trades/YYYY-MM-DD.parquet`, and `fundings/YYYY-MM-DD.parquet`.

Validate schema.

Convert timestamps.

Sort each stream.

Concatenate into a single event stream or process grouped timestamps with three event types.

Recommended event priority when timestamps match:

First: process trade events against orders that were already active before this timestamp.

Second: update orderbook state from snapshots at this timestamp.

Third: update funding state from funding rows at this timestamp.

Fourth: accrue funding and mark-to-market over the interval since the previous timestamp.

Fifth: let the strategy cancel/replace quotes using the updated book, updated funding, and past-only features.

Sixth: record metrics after strategy decisions, but before any same-timestamp fills from newly placed quotes.

This priority is intentionally conservative. It prevents the strategy from seeing a snapshot at time `t`, placing a quote, and being filled by a trade that also has timestamp `t`.

Detailed loop:

At start of day, initialize or carry forward state:

`q`, `cash`, `fees`, `funding_pnl`, average-cost inventory ledger, open orders, latest funding rate, latest valid orderbook, rolling feature windows.

For each timestamp group `t`:

Compute `Δt = t - previous_t`.

If there is a previous valid mark and funding state, accrue funding over `Δt`.

Process all trades at `t` in file order or stable sorted order:

For each trade, test active bid/ask eligibility.

Apply the chosen fill model.

For each fill, update order remaining quantity, inventory, cash, fees, realized PnL ledger, average cost, fill log, and inventory-limit state.

Apply orderbook snapshot(s) at `t`:

If multiple snapshots share timestamp, either use the last stable row by original order or process all in original sequence.

Validate book. If invalid, set `market_state.valid_book = False` and cancel quotes or disable new quotes.

Apply funding updates at `t`:

If multiple funding rows share timestamp, use the last one by original order.

Update rolling features:

Mid returns.

Book imbalance.

Trade imbalance from already processed trades.

Spread and volatility.

Mark-to-market:

`equity_t = cash + inventory * mid + funding_pnl - fees`

Record pre-strategy or post-market metrics.

Strategy step:

If no valid book, cancel all quotes and do not place new orders.

If kill switch active, cancel all quotes and do not place new orders.

Otherwise compute fair price, quote distances, inventory skew, target inventory, quote sizes, and quote prices.

Cancel stale or unsafe orders.

Place new passive orders if size is positive and price is valid.

Set `order_active_time = t + latency`.

Record order state.

At day boundary:

Record closing equity, inventory, realized/unrealized/funding split, fills, turnover, and risk metrics.

Do not reset inventory unless the project explicitly requires independent days. The default should carry inventory across days because a real bot would.

At final timestamp:

Mark residual inventory to mid.

Also compute conservative liquidation-adjusted equity:

If `q_final > 0`, liquidation value uses best bid.

If `q_final < 0`, liquidation value uses best ask.

Report both, with mid-mark as baseline and liquidation-adjusted as sensitivity.

7. Risk Controls

Essential controls for the take-home:

Max inventory:

`|q_t| <= q_max`

Never place a bid that can push inventory above `q_max`.

Never place an ask that can push inventory below `-q_max`.

Max quote size:

`order_size <= max_quote_size_eth`

Baseline:

`max_quote_size_eth = base_order_size_eth * 2`

Quote passivity:

Bid must be strictly below ask:

`bid_px <= A_t - tick`

Ask must be strictly above bid:

`ask_px >= B_t + tick`

Bad data stop:

Cancel all quotes and stop quoting if best bid/ask is missing, spread is negative, spread is zero, prices are non-positive, sizes are negative, or timestamp order is broken beyond repair.

Max drawdown kill switch:

If equity drawdown breaches:

`E_t - max(E_u, u≤t) <= -max_drawdown_usd`

then cancel all quotes and stop for the rest of the day or the rest of the backtest. Baseline:

`max_drawdown_usd = 100`, or `5% of q_max * initial_mid`.

Spread widening during volatility:

If rolling volatility is above a high threshold, increase quote distance:

`δ_t *= vol_widen_multiplier`

Baseline:

`vol_widen_multiplier = 2.0` when volatility exceeds rolling p95.

Adverse pressure side stop:

If buy pressure is extreme, stop quoting ask. If sell pressure is extreme, stop quoting bid. This is essential because market makers lose most when getting filled just before continuation moves.

End-of-day inventory handling:

In the last `eod_reduce_window_minutes = 15`, use reduce-only quoting:

If long, quote ask normally or slightly more aggressively; disable bid.

If short, quote bid normally or slightly more aggressively; disable ask.

Do not force taker liquidation in the baseline. Instead, report residual inventory and liquidation-adjusted PnL.

Optional controls:

Order-to-trade ratio limit. Useful for realism, but not necessary without exchange rate-limit data.

Max notional turnover. Useful if the strategy overtrades due to tiny spreads.

Funding exposure cap. Useful if funding signal tries to hold too much directional inventory.

Cooldown after large fill. Useful to avoid immediate refills after toxic trades.

8. Metrics and Report Output

Final tables:

Overall summary:

Total PnL.

Trading realized PnL.

Trading unrealized PnL.

Funding PnL.

Fees.

Liquidation-adjusted PnL.

Total fills.

Fill volume in ETH.

Turnover in USD.

Max inventory.

Mean absolute inventory.

Max drawdown.

Sharpe-like 1-minute metric.

Daily summary:

Date.

Starting equity.

Ending equity.

Daily PnL.

Realized trading PnL.

Unrealized trading PnL change.

Funding PnL.

Fees.

Number of bid fills.

Number of ask fills.

Bid volume ETH.

Ask volume ETH.

Average inventory.

Max absolute inventory.

Max drawdown.

Fill statistics:

Fill count.

Fill volume.

Bid fills versus ask fills.

Mean fill size.

Median fill size.

Average fill notional.

Average passive edge to mid:

For buy fills:

`edge = M_fill - fill_price`

For sell fills:

`edge = fill_price - M_fill`

Average realized spread after 1 second, 5 seconds, and 30 seconds:

For buy:

`RS_Δ = M_{t+Δ} - fill_price`

For sell:

`RS_Δ = fill_price - M_{t+Δ}`

Adverse selection after fills:

For buy:

`tox_Δ = M_fill - M_{t+Δ}`

For sell:

`tox_Δ = M_{t+Δ} - M_fill`

Positive toxicity means the mid moved against the market maker after the fill.

Inventory statistics:

Mean inventory.

Mean absolute inventory.

Standard deviation of inventory.

Minimum and maximum inventory.

Percentage of time at inventory limit.

Percentage of time long, short, flat.

Inventory autocorrelation or average holding time if easy.

Risk metrics:

Max drawdown.

Worst 1-minute PnL.

Best 1-minute PnL.

Standard deviation of 1-minute PnL.

PnL per turnover:

`PnL / total_turnover`

PnL per ETH traded:

`PnL / total_fill_volume_eth`

Plots:

Equity curve over time.

Daily equity curves.

Mid price with inventory overlay.

Inventory time series.

Histogram of inventory.

Histogram of spreads.

Quote distance over time.

Fill markers on mid price, with buys and sells distinguished.

Funding rate over time with inventory overlay.

Adverse selection curve: average post-fill realized spread at 1s, 5s, 30s.

Parameter summary table:

All fixed parameters.

Inferred tick size.

Fee assumption.

Latency assumption.

Fill model used.

Funding accrual assumption.

Convincing conclusions for an interviewer:

The best conclusion is not simply “PnL is positive.” A convincing conclusion says whether PnL comes from spread capture, inventory drift, funding, or mark-to-market luck.

A strong result would show positive or near-flat PnL under conservative queue fills, bounded inventory, small drawdown, bid/ask fill balance, and realized spread that stays positive after several seconds.

A weak but honest result can still pass if it explains that raw spread capture was overwhelmed by adverse selection, then shows which controls reduced losses.

The report should explicitly say whether the strategy is robust across all three days or only profitable on one day.

9. Parameter Plan

Use a small grid. Three days is too little data for aggressive optimization. The purpose is sensitivity analysis, not parameter mining.

Fixed baseline values:

`maker_fee_bps = 0.0`

`latency_ms = 250`

`base_order_size_eth = 0.10`

`q_max = 1.00 ETH`

`refresh_interval_seconds = 5`

`max_quote_age_seconds = 10`

`min_half_spread_ticks = 2`

`spread_mult = 1.0`

`W_vol = 60 seconds`

`τ_quote = 5 seconds`

`k_vol = 1.0`

`θ_inv = 1.5`

`funding_target_frac = 0.25`

`funding_scale = 1e-4`, subject to audit

`k_adv = 0.5`

`pressure_stop = 0.85`

`cooldown_seconds = 10`

Small sensitivity grid:

Quote spread / aggressiveness:

`spread_mult ∈ {1.0, 1.5, 2.0}`

Order size:

`base_order_size_eth ∈ {0.05, 0.10, 0.20}`

Inventory skew:

`θ_inv ∈ {0.75, 1.5, 3.0}`

Max inventory:

`q_max ∈ {0.5, 1.0, 2.0} ETH`

Refresh interval:

`refresh_interval_seconds ∈ {1, 5, 10}`

Volatility window:

`W_vol ∈ {30s, 60s, 300s}`

Funding tilt:

`funding_target_frac ∈ {0.0, 0.25, 0.50}`

Do not run the full Cartesian product as the main result. Use the fixed baseline plus one-at-a-time sensitivity. If time allows, run a small matrix of maybe 12 configurations:

Baseline.

Wider quotes.

Tighter quotes.

Smaller size.

Larger size.

Lower inventory skew.

Higher inventory skew.

No funding tilt.

Stronger funding tilt.

Shorter refresh.

Longer refresh.

Higher volatility buffer.

Avoid selecting the best configuration as “the strategy.” The main report should present the baseline and show sensitivity around it.

10. Validation Tests Before Trusting Results

PnL accounting test, long position:

Start with `cash = 0`, `q = 0`.

Buy `1 ETH @ 100`.

Cash becomes `-100`, inventory becomes `1`.

Mark at `102`.

Equity is `-100 + 1*102 = 2`.

Sell `1 ETH @ 103`.

Cash becomes `3`, inventory becomes `0`.

Realized trading PnL is `3`.

Equity is `3`.

PnL accounting test, short position:

Sell `2 ETH @ 100`.

Cash becomes `200`, inventory `-2`.

Buy `1 ETH @ 95`.

Cash becomes `105`, inventory `-1`.

Realized trading PnL is `5`.

If mark is `90`, unrealized PnL on remaining short is `10`.

Equity is `105 - 90 = 15`.

Realized plus unrealized is `15`.

Fee test:

With `maker_fee_bps = 1`, a fill of `1 ETH @ 100` adds:

`fee = 100 * 0.0001 = 0.01`

Total equity should be reduced by `0.01`.

Funding PnL test:

Long `1 ETH`, mark `2000`, positive funding `r = 0.0001`, funding period `8h`, elapsed `1h`.

`ΔF = -1 * 2000 * 0.0001 * (1/8) = -0.025 USD`

Short `1 ETH` under same conditions should receive `+0.025 USD`.

Simple fill test:

Live bid: `99`, size `1`.

Trade: `is_maker_ask = 0`, price `99`, size `0.4`.

Expected fill: buy `0.4 @ 99`.

Remaining bid size: `0.6`.

Next trade: `is_maker_ask = 0`, price `98.5`, size `1.0`.

Expected fill: buy `0.6 @ 99`.

Order done.

Direction test:

Live bid at `99`.

Trade: `is_maker_ask = 1`, price `101`, size `10`.

Expected bid fill: zero, because buy-aggressor trades hit asks, not bids.

Queue model test:

Live bid at `99`, size `1`.

At placement, visible bid queue at prices `>= 99` is `5 ETH`.

First sell-aggressor trade at `99`, size `3`.

Queue ahead becomes `2`; no fill.

Second sell-aggressor trade at `99`, size `4`.

First `2` consumes queue ahead. Remaining `2` reaches us. Fill `1`. Order complete.

Inventory limit test:

`q = 0.95`, `q_max = 1.00`, desired bid size `0.10`.

Expected bid size clipped to `0.05`.

If `q = 1.00`, expected bid size `0`.

Event ordering test:

At timestamp `t`, orderbook update arrives, strategy places bid at `99`.

Also at timestamp `t`, a sell trade at `99` exists.

Expected fill: zero, because the order was not active before timestamp `t`.

No-lookahead test:

Build a toy stream where the future trade imbalance would predict a move, but past imbalance does not. Strategy quotes must be identical whether future rows are present or truncated after current time.

Daily aggregation test:

End day 1 equity `100`, end day 2 equity `130`, end day 3 equity `120`.

Daily PnLs should be `100`, `30`, `-10` if starting equity is `0`.

Inventory should carry unless explicitly reset.

Mark-to-market test:

Long `0.5 ETH`, cash `-1000`, mark `2100`.

Equity is `-1000 + 0.5*2100 = 50`.

If mark changes to `2080`, equity becomes `40`.

Unrealized PnL changes by `-10`.

Bad data test:

Crossed book: `bid_1 = 101`, `ask_1 = 100`.

Expected behavior: cancel orders or stop quoting, no new quotes, no mid update from invalid book unless explicitly allowed.

11. Implementation Blueprint

Recommended project structure, without writing implementation code:

`README.md`

Explains assumptions, how to run audit, how to run baseline backtest, how to reproduce report, and where outputs are saved.

`config/default.yaml`

Single source of truth for parameters: fees, latency, tick inference, order size, inventory limits, spread parameters, funding parameters, fill model, risk controls, and reporting frequency.

`src/data_loader.py`

Loads daily parquet files.

Validates required columns.

Converts timestamps.

Concatenates days.

Returns typed dataframes or event records.

Does not contain strategy logic.

`src/data_audit.py`

Runs all checks from section 2.

Outputs an audit table and warnings.

Infers tick size.

Computes spread/depth/trade/funding diagnostics.

Controls whether the backtest is allowed to run.

`src/events.py`

Defines event types conceptually: orderbook snapshot, trade, funding update, timer/strategy decision.

Builds a deterministic chronological event sequence or timestamp-group iterator.

Owns same-timestamp priority rules.

`src/book_state.py`

Maintains latest valid orderbook.

Computes best bid/ask, mid, spread, microprice, depth, imbalance, and visible queue ahead.

Handles invalid snapshots.

`src/features.py`

Computes rolling volatility, trade imbalance, book imbalance, spread regime, jump detection, and funding state using past-only data.

`src/strategy.py`

Contains the market-making strategy.

Inputs: current book state, inventory, funding state, features, risk state, config.

Outputs: cancel requests and desired bid/ask orders.

No PnL accounting here.

`src/orders.py`

Defines live order state conceptually: side, price, original quantity, remaining quantity, placement time, active time, queue ahead, order ID, status.

Handles cancel/replace decisions.

`src/fill_model.py`

Implements simple fill model and conservative queue fill model.

Inputs: active orders, trade event, current queue state.

Outputs: fills.

Must be independent from accounting.

`src/accounting.py`

Maintains cash, inventory, average cost, realized trading PnL, unrealized trading PnL, funding PnL, fees, and equity.

Provides mark-to-market snapshots.

`src/risk.py`

Implements max inventory, quote clipping, drawdown kill switch, volatility cooldown, bad-data stop, and end-of-day reduce-only mode.

`src/simulator.py`

Owns the event loop.

Coordinates data, book, features, strategy, fill model, accounting, risk, and metrics recording.

Does not contain parameter definitions.

`src/metrics.py`

Aggregates fills, inventory, PnL, drawdown, turnover, realized spread, adverse selection, and daily summaries.

`src/reporting.py`

Creates tables and plots.

Exports `summary.csv`, `daily_pnl.csv`, `fills.csv`, `equity_curve.csv`, and plots.

`notebooks/analysis.ipynb`

Optional. Used only for exploration and report drafting, not as the core implementation.

`reports/final_report.md` or `reports/final_report.pdf`

Final take-home report with assumptions, audit results, strategy description, metrics, plots, sensitivity, and conclusions.

`tests/test_accounting.py`

Toy examples for long/short/fees/funding.

`tests/test_fill_model.py`

Simple and queue fill examples.

`tests/test_event_ordering.py`

Same-timestamp and latency tests.

`tests/test_inventory_limits.py`

Order clipping and quote disabling.

`tests/test_daily_aggregation.py`

Day boundary and carried inventory tests.

`tests/test_no_lookahead.py`

Feature truncation and future-data checks.

12. Reviewer Strategy

What will make the take-home look strong:

State assumptions honestly. The reviewer will know that exact queue position cannot be recovered from L2 snapshots and trades alone. Acknowledging this is a strength, not a weakness.

Use the conservative fill model as the main result. The simple fill model can be shown as an optimistic upper bound, but the report should not rely on it.

Decompose PnL clearly. Show realized trading, unrealized trading, funding, and fees separately. A single total PnL number is not enough.

Report adverse selection. A market-making strategy that earns spread but loses after fills is not robust. Showing realized spread after 1s, 5s, and 30s is highly valuable.

Make config reproducible. Every number in the report should map back to a config parameter.

Show inventory discipline. Interviewers will penalize a strategy that is secretly a directional long/short bet. Inventory time series and distribution are essential.

Include sensitivity analysis, but do not overfit. The right framing is: “Here is a baseline, and here is how it changes under wider quotes, smaller size, no funding tilt, and conservative fills.”

Keep the strategy simple. A clean, robust market-making simulator with transparent assumptions is better than a complex alpha model trained on three days.

Biggest traps:

Assuming every trade through your price fully fills you immediately.

Allowing orders placed at timestamp `t` to be filled by trades at timestamp `t`.

Using future orderbook snapshots to decide whether an old quote would have filled.

Ignoring queue ahead at the best bid/ask.

Reporting only total PnL without realized/unrealized/funding split.

Treating mark-to-market inventory gains as spread capture.

Over-optimizing parameters on three days.

Forgetting fees or silently assuming zero fees.

Forcing end-of-day liquidation without separating taker cost from maker strategy.

Letting inventory drift to max and calling the result market making.

Not validating trade/book timestamp alignment.

Ignoring funding units and payment convention.

13. Final Recommendation

Recommended baseline strategy:

Use a single-level, maker-only market maker with fair price:

`fair = mid + 0.5 * (microprice - mid) + 0.25 * half_spread * trade_imbalance`

Use adaptive half-spread:

`δ = max(2 ticks, 1.0 * current_half_spread, volatility_buffer)`

Use inventory reservation price:

`reservation = fair - θ_inv * δ * (q - q_target) / q_max`

with:

`θ_inv = 1.5`

`q_max = 1.0 ETH`

`base_order_size = 0.10 ETH`

`refresh_interval = 5s`

Use funding only as target-inventory tilt, not as a standalone directional trade:

`q_target = -0.25 * q_max * tanh(funding_rate / funding_scale)`

Recommended fill model:

Use the conservative queue-ahead model as the official result. Use the simple trade-through model only as a comparison.

Recommended PnL accounting method:

Use cash plus mark-to-market equity as the source of truth:

`Equity = Cash + Inventory * Mid + Funding - Fees`

Also maintain average-cost realized and unrealized trading PnL so the report can explain where PnL came from.

Minimum viable deliverable:

A data audit.

A deterministic event-driven simulator.

One conservative fill model.

One baseline market-making strategy.

Full PnL decomposition.

Daily and total metrics.

Inventory and fill statistics.

Equity, inventory, and fill plots.

A short report explaining assumptions, limitations, and results.

High-upside enhancements if time remains:

Add simple fill model as optimistic upper bound.

Add one-at-a-time parameter sensitivity.

Add adverse-selection analysis after fills.

Add end-of-period liquidation-adjusted PnL.

Add no-funding versus funding-tilt comparison.

Add volatility-regime breakdown: quiet periods versus high-volatility periods.

Add maker-fee sensitivity.

The strongest version of this take-home is not the most complicated bot. It is a conservative, reproducible simulator with honest fill assumptions, tight PnL accounting, controlled inventory, and a clear explanation of why the reported PnL should or should not be trusted.

[1]: https://github.com/hlemonnier/eth-perp-market-making-takehome/blob/main/README.md "eth-perp-market-making-takehome/README.md at main · hlemonnier/eth-perp-market-making-takehome · GitHub"
