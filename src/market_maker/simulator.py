from __future__ import annotations

from dataclasses import dataclass, field
from math import tanh

import pandas as pd

from market_maker.accounting import AccountingState
from market_maker.book_state import LEVELS, BookState
from market_maker.config import BacktestConfig
from market_maker.data_loader import MarketData
from market_maker.features import RollingFeatures
from market_maker.fill_model import FillModel, TradeEvent
from market_maker.metrics import MetricsBundle, summarize_metrics
from market_maker.orders import Fill, LiveOrder, Side
from market_maker.risk import RiskState
from market_maker.strategy import MarketMakingStrategy, QuoteDecision


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    fills: pd.DataFrame
    orders: pd.DataFrame
    metrics: MetricsBundle
    final_liquidation_adjusted_equity: float
    mark_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    final_forced_flat_equity: float | None = None


class Simulator:
    def __init__(self, data: MarketData, config: BacktestConfig, tick_size: float):
        self.data = data
        self.config = config
        self.tick_size = tick_size
        self.account = AccountingState(maker_fee_bps=config.execution.maker_fee_bps)
        self.book = BookState()
        self.features = RollingFeatures(mid_window_seconds=config.strategy.vol_window_seconds)
        self.fill_model = FillModel(config.execution.fill_model, config.execution.queue_depletion_fraction)
        self.strategy = MarketMakingStrategy(config.strategy, config.risk, tick_size, maker_fee_bps=config.execution.maker_fee_bps)
        self.risk = RiskState(config.risk)
        self.active_orders: dict[Side, LiveOrder | None] = {Side.BID: None, Side.ASK: None}
        self.latest_funding_rate = 0.0
        self.previous_timestamp: pd.Timestamp | None = None
        self.previous_mark: float | None = None
        self.next_order_id = 1
        self.last_refresh_time: pd.Timestamp | None = None
        self.last_bbo: tuple[float, float] | None = None
        self.force_refresh = False
        self.latency_delta = pd.Timedelta(milliseconds=config.execution.latency_ms)
        cancel_latency_ms = config.execution.cancel_latency_ms
        if cancel_latency_ms is None:
            cancel_latency_ms = config.execution.latency_ms
        self.cancel_latency_delta = pd.Timedelta(milliseconds=cancel_latency_ms)
        self.stale_book_max_age_ms = float(config.execution.stale_book_max_age_ms)
        self.report_interval_ns = pd.Timedelta(config.execution.report_frequency).value
        self.next_report_time_ns: int | None = None
        self.refresh_interval_ns = config.strategy.refresh_interval_seconds * _NS_PER_SECOND
        self.max_quote_age_ns = config.strategy.max_quote_age_seconds * _NS_PER_SECOND
        self.last_timestamp: pd.Timestamp | None = None
        self.last_half_distance: float | None = None
        self.last_funding_target: float | None = None
        self.quote_state_dirty = True
        self.equity_rows: list[dict[str, object]] = []
        self.mark_rows: list[dict[str, object]] = []
        self.fill_rows: list[dict[str, object]] = []
        self.order_rows: list[dict[str, object]] = []
        self.daily_peak_equity: dict[str, float] = {}
        self.daily_max_drawdown_loss: dict[str, float] = {}

    def run(self) -> BacktestResult:
        arrays = _PreparedArrays.from_market_data(self.data)
        book_i = trade_i = funding_i = 0
        while book_i < arrays.book_count or trade_i < arrays.trade_count or funding_i < arrays.funding_count:
            next_ns = min(
                arrays.book_times[book_i] if book_i < arrays.book_count else _MAX_NS,
                arrays.trade_times[trade_i] if trade_i < arrays.trade_count else _MAX_NS,
                arrays.funding_times[funding_i] if funding_i < arrays.funding_count else _MAX_NS,
            )
            timestamp = pd.Timestamp(next_ns, unit="ns", tz="UTC")
            self._complete_effective_cancels(timestamp)
            self._accrue_funding(timestamp)
            self._cancel_expired_orders(timestamp)
            self._complete_effective_cancels(timestamp)
            self._enforce_reduce_only_orders(timestamp)
            self._enforce_stale_book_guard(timestamp)

            while trade_i < arrays.trade_count and arrays.trade_times[trade_i] == next_ns:
                self._process_trade_values(
                    timestamp,
                    price=float(arrays.trade_prices[trade_i]),
                    size=float(arrays.trade_sizes[trade_i]),
                    is_maker_ask=int(arrays.trade_is_maker_ask[trade_i]),
                )
                trade_i += 1

            while book_i < arrays.book_count and arrays.book_times[book_i] == next_ns:
                self._process_orderbook_values(
                    timestamp,
                    arrays.bid_prices[book_i],
                    arrays.bid_quantities[book_i],
                    arrays.ask_prices[book_i],
                    arrays.ask_quantities[book_i],
                )
                book_i += 1

            while funding_i < arrays.funding_count and arrays.funding_times[funding_i] == next_ns:
                self.latest_funding_rate = float(arrays.funding_rates[funding_i])
                self.quote_state_dirty = True
                funding_i += 1

            self._update_mark_and_strategy(timestamp)
            self.previous_timestamp = timestamp
            self.last_timestamp = timestamp

        if self.last_timestamp is not None:
            self._record(self.last_timestamp, None, None, force=True)

        liquidation_equity = self._liquidation_equity()
        equity_curve = pd.DataFrame(self.equity_rows)
        mark_curve = pd.DataFrame(self.mark_rows)
        if not mark_curve.empty:
            mark_curve["timestamp"] = pd.to_datetime(mark_curve["timestamp"], utc=True)
        fills = pd.DataFrame(self.fill_rows)
        if not fills.empty:
            fills["timestamp"] = pd.to_datetime(fills["timestamp"], utc=True)
            fills = _add_fill_markouts(fills, mark_curve, self.stale_book_max_age_ms)
        else:
            fills = _empty_fills_with_diagnostic_columns()
        orders = pd.DataFrame(self.order_rows)
        forced_flat_equity = self._forced_flat_equity()
        metrics = summarize_metrics(
            equity_curve,
            fills,
            orders,
            liquidation_equity,
            self.risk.max_drawdown_loss,
            mark_curve,
            self.daily_max_drawdown_loss,
            forced_flat_equity,
        )
        return BacktestResult(equity_curve, fills, orders, metrics, liquidation_equity, mark_curve, forced_flat_equity)

    def _accrue_funding(self, timestamp: pd.Timestamp) -> None:
        if self.previous_timestamp is None or self.previous_mark is None:
            return
        elapsed = (timestamp.value - self.previous_timestamp.value) / 1_000_000_000.0
        self.account.accrue_funding(
            elapsed_seconds=elapsed,
            mark_price=self.previous_mark,
            funding_rate=self.latest_funding_rate,
            funding_period_hours=self.config.execution.funding_period_hours,
        )

    def _process_trades(self, timestamp: pd.Timestamp, indices: list[int]) -> None:
        for index in indices:
            row = self.data.trades.iloc[index]
            self._process_trade_values(timestamp, float(row["price"]), float(row["size"]), int(row["is_maker_ask"]))

    def _process_trade_values(self, timestamp: pd.Timestamp, price: float, size: float, is_maker_ask: int) -> None:
        trade = TradeEvent(timestamp=timestamp, price=price, size=size, is_maker_ask=is_maker_ask)
        for side in [Side.BID, Side.ASK]:
            order = self.active_orders.get(side)
            order_status_at_fill = order.state_at(timestamp) if order is not None else None
            fill = self.fill_model.process_trade(order, trade, self._current_mid(timestamp))
            if fill is not None:
                self._apply_fill(fill, order_status_at_fill)
        self.features.update_trade(timestamp, trade.is_maker_ask, trade.size)
        self.quote_state_dirty = True
        self._enforce_pressure_stop(timestamp)
        self._enforce_expected_edge(timestamp)

    def _apply_fill(self, fill: Fill, order_status_at_fill: str | None = None) -> None:
        order = self.active_orders.get(fill.side)
        inventory_before = self.account.inventory
        pressure_at_fill = self._current_pressure()
        book_age_ms = None
        if self.book.timestamp is not None:
            book_age_ms = (fill.timestamp - self.book.timestamp).total_seconds() * 1000.0
        order_age_ms = None
        quote_age_ms = None
        if order is not None:
            order_age_ms = (fill.timestamp - order.created_time).total_seconds() * 1000.0
            quote_age_ms = order_age_ms
        self.account.apply_fill(fill)
        self.force_refresh = True
        self.fill_rows.append(
            {
                "timestamp": fill.timestamp,
                "order_id": fill.order_id,
                "side": fill.side.value,
                "price": fill.price,
                "quantity": fill.quantity,
                "signed_quantity": fill.signed_quantity,
                "trade_price": fill.trade_price,
                "trade_size": fill.trade_size,
                "best_bid": self.book.best_bid if self.book.valid else None,
                "best_ask": self.book.best_ask if self.book.valid else None,
                "spread_at_fill": self.book.spread if self.book.valid else None,
                "queue_ahead_before": fill.queue_ahead_before,
                "queue_ahead_before_fill": fill.queue_ahead_before,
                "queue_ahead_after": fill.queue_ahead_after,
                "queue_ahead_initial": None if order is None else order.queue_ahead_initial,
                "mid_at_fill": fill.mid_at_fill,
                "pressure_at_placement": None if order is None else order.placement_pressure,
                "pressure_at_fill": pressure_at_fill,
                "trade_imbalance_at_fill": self.features.trade_imbalance(),
                "microprice_at_fill": self.book.microprice if self.book.valid else None,
                "inventory_before": inventory_before,
                "cash_after": self.account.cash,
                "inventory_after": self.account.inventory,
                "realized_trading_pnl_after": self.account.realized_trading_pnl,
                "quote_age_ms": quote_age_ms,
                "book_age_ms": book_age_ms,
                "order_age_ms": order_age_ms,
                "fill_model": self.fill_model.name,
                "queue_depletion_fraction": self.fill_model.queue_depletion_fraction,
                "order_status_at_fill": order_status_at_fill,
                "cancel_requested_time": None if order is None else order.cancel_requested_time,
                "cancel_effective_time": None if order is None else order.cancel_effective_time,
                "cancel_reason": None if order is None else order.cancel_reason,
                "is_pending_cancel_fill": bool(order_status_at_fill == "pending_cancel"),
                "is_pressure_stop_violation": bool(
                    self._is_pressure_stop_violation(fill.side, pressure_at_fill) and order_status_at_fill != "pending_cancel"
                ),
                "is_pending_cancel_pressure_fill": bool(
                    self._is_pressure_stop_violation(fill.side, pressure_at_fill) and order_status_at_fill == "pending_cancel"
                ),
                "stale_book_at_fill": self._book_is_stale(fill.timestamp),
            }
        )
        if order is not None and order.status == "filled":
            self.active_orders[fill.side] = None

    def _process_orderbooks(self, indices: list[int]) -> None:
        for index in indices:
            row = self.data.orderbook.iloc[index]
            valid = self.book.update_from_row(row)
            if not valid:
                self._cancel_all("invalid_book", pd.Timestamp(row["datetime"]))
            else:
                self.features.update_mid(pd.Timestamp(row["datetime"]), self.book.mid)
                self.quote_state_dirty = True
                self._apply_book_queue_depletion(pd.Timestamp(row["datetime"]))
                self._record_mark(self.book.timestamp)
                self._enforce_pressure_stop(pd.Timestamp(row["datetime"]))
                self._enforce_expected_edge(pd.Timestamp(row["datetime"]))
        if self.book.valid:
            self._cancel_crossed_quotes(self.book.timestamp)

    def _process_orderbook_values(
        self,
        timestamp: pd.Timestamp,
        bid_prices,
        bid_quantities,
        ask_prices,
        ask_quantities,
    ) -> None:
        valid = self.book.fast_update_from_arrays(timestamp, bid_prices, bid_quantities, ask_prices, ask_quantities)
        if not valid:
            self._cancel_all("invalid_book", timestamp)
        elif self.book.valid:
            self.features.update_mid(timestamp, self.book.mid)
            self.quote_state_dirty = True
            self._apply_book_queue_depletion(timestamp)
            self._record_mark(timestamp)
            self._enforce_pressure_stop(timestamp)
            self._enforce_expected_edge(timestamp)
            self._cancel_crossed_quotes(timestamp)

    def _process_fundings(self, indices: list[int]) -> None:
        for index in indices:
            self.latest_funding_rate = float(self.data.fundings.iloc[index]["funding_rate"])
            self.quote_state_dirty = True

    def _update_mark_and_strategy(self, timestamp: pd.Timestamp) -> None:
        if not self.book.valid:
            self._record(timestamp, None, None)
            return

        if self._book_is_stale(timestamp):
            decision = QuoteDecision(
                bid_price=None,
                bid_size=0.0,
                ask_price=None,
                ask_size=0.0,
                fair_price=None,
                reservation_price=None,
                half_distance=None,
                funding_target=0.0,
                pressure=self._current_pressure(),
                reason="stale_book",
            )
            self._cancel_all("stale_book", timestamp)
            self.force_refresh = False
            self.quote_state_dirty = True
            self._record(timestamp, decision, equity=None)
            return

        self.previous_mark = self.book.mid
        equity = self.account.equity(self.book.mid)
        self.risk.update_drawdown(timestamp, equity)
        self._update_daily_drawdown(timestamp, equity)

        if self.risk.kill_switch_active:
            decision = QuoteDecision(
                bid_price=None,
                bid_size=0.0,
                ask_price=None,
                ask_size=0.0,
                fair_price=None,
                reservation_price=None,
                half_distance=None,
                funding_target=0.0,
                pressure=0.0,
                reason="kill_switch",
            )
            self._cancel_all("kill_switch", timestamp)
            self.force_refresh = False
            self.quote_state_dirty = False
            self._record(timestamp, decision, equity)
            return

        decision: QuoteDecision | None = None
        if self._should_refresh(timestamp):
            decision = self.strategy.quote(
                timestamp=timestamp,
                book=self.book,
                account=self.account,
                features=self.features,
                latest_funding_rate=self.latest_funding_rate,
                risk=self.risk,
                day_end=self._day_end(timestamp),
            )
            self.last_half_distance = decision.half_distance
            self.last_funding_target = decision.funding_target
            if decision.reason == "ok":
                self._reconcile_orders(timestamp, decision)
            else:
                self._cancel_all(decision.reason, timestamp)
            self.last_refresh_time = timestamp
            self.last_bbo = (self.book.best_bid, self.book.best_ask)
            self.force_refresh = False
            self.quote_state_dirty = False

        self._record(timestamp, decision, equity)

    def _should_refresh(self, timestamp: pd.Timestamp) -> bool:
        if not self.book.valid:
            return False
        if self._book_is_stale(timestamp):
            return False
        if self.force_refresh:
            return True
        open_orders = [order for order in self.active_orders.values() if self._is_open_order(order)]
        if self.last_refresh_time is None:
            return True
        timestamp_ns = timestamp.value
        elapsed_ns = timestamp_ns - self.last_refresh_time.value
        if not open_orders:
            return elapsed_ns >= self.refresh_interval_ns
        if elapsed_ns >= self.refresh_interval_ns:
            return True
        if any(timestamp_ns - order.created_time.value >= self.max_quote_age_ns for order in open_orders):
            return True
        if self.last_bbo is not None:
            bid_move = abs(self.book.best_bid - self.last_bbo[0]) / self.tick_size
            ask_move = abs(self.book.best_ask - self.last_bbo[1]) / self.tick_size
            if max(bid_move, ask_move) >= self.config.strategy.requote_bbo_ticks:
                return True
        if not self.quote_state_dirty:
            return False
        current_half_distance, current_target = self._current_quote_state()
        if (
            current_half_distance is not None
            and self.last_half_distance is not None
            and abs(current_half_distance - self.last_half_distance) / self.tick_size >= self.config.strategy.requote_delta_ticks
        ):
            return True
        if (
            current_target is not None
            and self.last_funding_target is not None
            and abs(current_target - self.last_funding_target) > self.config.strategy.funding_retarget_threshold
        ):
            return True
        return False

    def _current_quote_state(self) -> tuple[float | None, float | None]:
        if not self.book.valid:
            return None, None
        cfg = self.config.strategy
        funding_z = tanh(self.latest_funding_rate / cfg.funding_scale) if cfg.funding_scale else 0.0
        q_target = max(-cfg.q_max / 2.0, min(cfg.q_max / 2.0, -cfg.funding_target_frac * cfg.q_max * funding_z))
        vol_buffer = self.features.volatility_buffer(cfg.quote_horizon_seconds, cfg.k_vol)
        half_distance = max(cfg.min_half_spread_ticks * self.tick_size, cfg.spread_mult * self.book.half_spread, vol_buffer)
        if self.features.high_volatility():
            half_distance *= self.config.risk.vol_widen_multiplier
        return half_distance, q_target

    def _current_pressure(self) -> float:
        if not self.book.valid:
            return 0.0
        cfg = self.config.strategy
        return float(cfg.w_book * self.book.top_imbalance + cfg.w_trade * self.features.trade_imbalance())

    def _enforce_pressure_stop(self, timestamp: pd.Timestamp) -> None:
        if not self.book.valid:
            return
        pressure = self._current_pressure()
        threshold = self.config.strategy.pressure_stop
        if pressure < -threshold:
            self._cancel_order(Side.BID, "pressure_stop_bid", timestamp)
        if pressure > threshold:
            self._cancel_order(Side.ASK, "pressure_stop_ask", timestamp)

    def _enforce_expected_edge(self, timestamp: pd.Timestamp) -> None:
        if not self.book.valid or self._book_is_stale(timestamp):
            return
        open_quote_sides = [
            side
            for side, order in self.active_orders.items()
            if order is not None and order.status in {"pending_new", "live"} and order.remaining_quantity > 1e-12
        ]
        if not open_quote_sides:
            return
        decision = self.strategy.quote(
            timestamp=timestamp,
            book=self.book,
            account=self.account,
            features=self.features,
            latest_funding_rate=self.latest_funding_rate,
            risk=self.risk,
            day_end=self._day_end(timestamp),
        )
        if decision.reason != "ok":
            self._cancel_all(f"expected_edge_{decision.reason}", timestamp)
            return
        if Side.BID in open_quote_sides and (decision.bid_price is None or decision.bid_size <= 1e-12):
            self._cancel_order(Side.BID, "expected_edge_bid", timestamp)
        if Side.ASK in open_quote_sides and (decision.ask_price is None or decision.ask_size <= 1e-12):
            self._cancel_order(Side.ASK, "expected_edge_ask", timestamp)

    def _is_pressure_stop_violation(self, side: Side, pressure: float) -> bool:
        threshold = self.config.strategy.pressure_stop
        if side is Side.BID:
            return pressure < -threshold
        return pressure > threshold

    @staticmethod
    def _is_open_order(order: LiveOrder | None) -> bool:
        return order is not None and order.status in {"pending_new", "live", "pending_cancel"} and order.remaining_quantity > 1e-12

    def _book_age_ms(self, timestamp: pd.Timestamp) -> float | None:
        if self.book.timestamp is None:
            return None
        return max(0.0, (timestamp - self.book.timestamp).total_seconds() * 1000.0)

    def _book_is_stale(self, timestamp: pd.Timestamp) -> bool:
        if self.stale_book_max_age_ms <= 0 or not self.book.valid:
            return False
        age_ms = self._book_age_ms(timestamp)
        return age_ms is not None and age_ms > self.stale_book_max_age_ms

    def _enforce_stale_book_guard(self, timestamp: pd.Timestamp) -> None:
        if self._book_is_stale(timestamp):
            self._cancel_all("stale_book", timestamp)

    def _apply_book_queue_depletion(self, timestamp: pd.Timestamp) -> None:
        if self.fill_model.name not in {"partial_queue", "calibrated_queue"}:
            return
        fraction = self.fill_model.queue_depletion_fraction
        if fraction <= 0.0 or not self.book.valid:
            return
        for order in self.active_orders.values():
            if not self._is_open_order(order):
                continue
            current_visible = self.book.queue_ahead(order.side, order.price)
            if timestamp < order.active_time:
                order.last_known_book_time = timestamp
                order.last_visible_queue_ahead = current_visible
                continue
            order.refresh_state(timestamp)
            previous_visible = order.last_visible_queue_ahead
            order.last_known_book_time = timestamp
            order.last_visible_queue_ahead = current_visible
            if previous_visible is None:
                continue
            visible_reduction = max(0.0, previous_visible - current_visible)
            if visible_reduction > 0.0:
                order.queue_ahead = max(0.0, order.queue_ahead - fraction * visible_reduction)

    def _place_orders(self, timestamp: pd.Timestamp, decision: QuoteDecision) -> None:
        active_time = timestamp + self.latency_delta
        if decision.bid_price is not None and decision.bid_size > 1e-12:
            self._place_order(timestamp, active_time, Side.BID, decision.bid_price, decision.bid_size)
        if decision.ask_price is not None and decision.ask_size > 1e-12:
            self._place_order(timestamp, active_time, Side.ASK, decision.ask_price, decision.ask_size)

    def _reconcile_orders(self, timestamp: pd.Timestamp, decision: QuoteDecision) -> None:
        desired = {
            Side.BID: (decision.bid_price, decision.bid_size),
            Side.ASK: (decision.ask_price, decision.ask_size),
        }
        active_time = timestamp + self.latency_delta
        keep_ticks = max(0, self.config.strategy.requote_delta_ticks)
        for side, (price, size) in desired.items():
            existing = self.active_orders.get(side)
            if price is None or size <= 1e-12:
                self._cancel_order(side, "refresh_no_desired_quote", timestamp)
                continue
            if existing is not None and existing.status in {"pending_new", "live"}:
                price_distance_ticks = abs(existing.price - price) / self.tick_size
                order_age_ns = timestamp.value - existing.created_time.value
                if price_distance_ticks <= keep_ticks and order_age_ns < self.max_quote_age_ns:
                    if existing.remaining_quantity > size:
                        existing.remaining_quantity = size
                        self.order_rows.append(
                            {
                                "timestamp": timestamp,
                                "order_id": existing.order_id,
                                "event": "resized",
                                "side": side.value,
                                "price": existing.price,
                                "quantity": existing.remaining_quantity,
                                "active_time": existing.active_time,
                                "queue_ahead": existing.queue_ahead,
                                "reason": "preserve_queue_priority",
                            }
                        )
                    continue
                cancel_reason = "quote_age_expired" if price_distance_ticks <= keep_ticks else "refresh_reprice"
                cancel_time = self._quote_expiry_time(existing) if cancel_reason == "quote_age_expired" else timestamp
                self._cancel_order(side, cancel_reason, cancel_time)
                if self.active_orders.get(side) is not None:
                    continue
            else:
                self._cancel_order(side, "refresh_reprice", timestamp)
                if self.active_orders.get(side) is not None:
                    continue
            self._place_order(timestamp, active_time, side, price, size)

    def _place_order(self, timestamp: pd.Timestamp, active_time: pd.Timestamp, side: Side, price: float, size: float) -> None:
        queue_ahead = self.book.queue_ahead(side, float(price))
        order = LiveOrder(
            order_id=self.next_order_id,
            side=side,
            price=float(price),
            original_quantity=float(size),
            remaining_quantity=float(size),
            created_time=timestamp,
            active_time=active_time,
            queue_ahead=queue_ahead,
            queue_ahead_initial=queue_ahead,
            placement_pressure=self._current_pressure(),
            placement_trade_imbalance=self.features.trade_imbalance(),
            placement_microprice=self.book.microprice if self.book.valid else None,
            last_known_book_time=self.book.timestamp,
            last_visible_queue_ahead=queue_ahead,
        )
        self.next_order_id += 1
        self.active_orders[side] = order
        self.order_rows.append(
            {
                "timestamp": timestamp,
                "order_id": order.order_id,
                "event": "placed",
                "side": side.value,
                "price": order.price,
                "quantity": order.original_quantity,
                "active_time": active_time,
                "queue_ahead": order.queue_ahead,
                "new_order_time": order.new_order_time,
                "order_state": order.state_at(timestamp),
            }
        )

    def _cancel_all(self, reason: str, timestamp: pd.Timestamp | None = None) -> None:
        for side, order in list(self.active_orders.items()):
            self._cancel_order(side, reason, timestamp)

    def _cancel_order(self, side: Side, reason: str, timestamp: pd.Timestamp | None = None) -> None:
        order = self.active_orders.get(side)
        cancel_ts = timestamp if timestamp is not None else self.book.timestamp
        if cancel_ts is None:
            cancel_ts = self.last_timestamp
        if order is not None and self._is_open_order(order) and cancel_ts is not None:
            if order.status == "pending_cancel":
                return
            cancel_effective_time = cancel_ts + self.cancel_latency_delta
            if self.cancel_latency_delta > pd.Timedelta(0):
                order.request_cancel(cancel_ts, cancel_effective_time, reason)
                self.order_rows.append(
                    {
                        "timestamp": cancel_ts,
                        "order_id": order.order_id,
                        "event": "cancel_requested",
                        "side": side.value,
                        "price": order.price,
                        "quantity": order.remaining_quantity,
                        "active_time": order.active_time,
                        "queue_ahead": order.queue_ahead,
                        "reason": reason,
                        "new_order_time": order.new_order_time,
                        "order_state": order.state_at(cancel_ts),
                        "cancel_requested_time": order.cancel_requested_time,
                        "cancel_effective_time": cancel_effective_time,
                    }
                )
                self.force_refresh = True
                return
            order.request_cancel(cancel_ts, cancel_effective_time, reason)
            self._finalize_cancel(side, cancel_effective_time)
            self.force_refresh = True

    def _complete_effective_cancels(self, timestamp: pd.Timestamp) -> None:
        completed = False
        for side, order in list(self.active_orders.items()):
            if order is None or order.status != "pending_cancel" or order.cancel_effective_time is None:
                continue
            if timestamp < order.cancel_effective_time:
                continue
            self._finalize_cancel(side, order.cancel_effective_time)
            completed = True
        if completed:
            self.force_refresh = True

    def _finalize_cancel(self, side: Side, timestamp: pd.Timestamp) -> None:
        order = self.active_orders.get(side)
        if order is None or order.status != "pending_cancel":
            return
        order.complete_cancel()
        self.order_rows.append(
            {
                "timestamp": timestamp,
                "order_id": order.order_id,
                "event": "cancelled",
                "side": side.value,
                "price": order.price,
                "quantity": order.remaining_quantity,
                "active_time": order.active_time,
                "queue_ahead": order.queue_ahead,
                "reason": order.cancel_reason,
                "new_order_time": order.new_order_time,
                "order_state": order.status,
                "cancel_requested_time": order.cancel_requested_time,
                "cancel_effective_time": order.cancel_effective_time,
            }
        )
        self.active_orders[side] = None

    def _cancel_expired_orders(self, timestamp: pd.Timestamp) -> None:
        expired = False
        for side, order in list(self.active_orders.items()):
            if not self._is_open_order(order) or order.status == "pending_cancel":
                continue
            if timestamp.value - order.created_time.value >= self.max_quote_age_ns:
                self._cancel_order(side, "quote_age_expired", self._quote_expiry_time(order))
                expired = True
        if expired:
            self.force_refresh = True

    def _quote_expiry_time(self, order: LiveOrder) -> pd.Timestamp:
        return pd.Timestamp(order.created_time.value + self.max_quote_age_ns, unit="ns", tz="UTC")

    def _update_daily_drawdown(self, timestamp: pd.Timestamp, equity: float) -> None:
        date_key = timestamp.date().isoformat()
        peak = self.daily_peak_equity.get(date_key)
        if peak is None or equity > peak:
            peak = equity
            self.daily_peak_equity[date_key] = peak
        loss = peak - equity
        if loss > self.daily_max_drawdown_loss.get(date_key, 0.0):
            self.daily_max_drawdown_loss[date_key] = float(loss)

    def _enforce_reduce_only_orders(self, timestamp: pd.Timestamp) -> None:
        if not self.config.risk.eod_reduce_window_minutes:
            return
        if not any(self._is_open_order(order) for order in self.active_orders.values()):
            return
        if not self._in_reduce_only_window(timestamp):
            return
        inventory = self.account.inventory
        eps = 1e-12
        if inventory > eps:
            self._cancel_order(Side.BID, "eod_reduce_only", timestamp)
            self._cap_order_size(Side.ASK, inventory, "eod_reduce_only_cap", timestamp)
        elif inventory < -eps:
            self._cancel_order(Side.ASK, "eod_reduce_only", timestamp)
            self._cap_order_size(Side.BID, -inventory, "eod_reduce_only_cap", timestamp)
        else:
            self._cancel_all("eod_reduce_only_flat", timestamp)

    def _cap_order_size(self, side: Side, max_size: float, reason: str, timestamp: pd.Timestamp) -> None:
        order = self.active_orders.get(side)
        if order is None or order.status not in {"pending_new", "live"}:
            return
        if max_size <= 1e-12:
            self._cancel_order(side, reason, timestamp)
            return
        if order.remaining_quantity <= max_size + 1e-12:
            return
        order.remaining_quantity = float(max_size)
        self.order_rows.append(
            {
                "timestamp": timestamp,
                "order_id": order.order_id,
                "event": "resized",
                "side": side.value,
                "price": order.price,
                "quantity": order.remaining_quantity,
                "active_time": order.active_time,
                "queue_ahead": order.queue_ahead,
                "reason": reason,
            }
        )

    def _cancel_crossed_quotes(self, timestamp: pd.Timestamp | None = None) -> None:
        bid = self.active_orders.get(Side.BID)
        ask = self.active_orders.get(Side.ASK)
        if bid is not None and bid.status in {"pending_new", "live"} and bid.price >= self.book.best_ask:
            self._cancel_order(Side.BID, "quote_crossed_after_book_update", timestamp)
        if ask is not None and ask.status in {"pending_new", "live"} and ask.price <= self.book.best_bid:
            self._cancel_order(Side.ASK, "quote_crossed_after_book_update", timestamp)

    def _record(self, timestamp: pd.Timestamp, decision: QuoteDecision | None, equity: float | None, force: bool = False) -> None:
        if not force and self.report_interval_ns > 0:
            timestamp_ns = timestamp.value
            if self.next_report_time_ns is None:
                self.next_report_time_ns = timestamp_ns
            if timestamp_ns < self.next_report_time_ns:
                return
            while self.next_report_time_ns <= timestamp_ns:
                self.next_report_time_ns += self.report_interval_ns

        if self.book.valid:
            mark = self.book.mid
            equity_value = self.account.equity(mark)
            unrealized = self.account.unrealized_trading_pnl(mark)
            spread = self.book.spread
            best_bid = self.book.best_bid
            best_ask = self.book.best_ask
            mid = mark
        else:
            equity_value = equity if equity is not None else float("nan")
            unrealized = float("nan")
            spread = float("nan")
            best_bid = float("nan")
            best_ask = float("nan")
            mid = float("nan")

        bid_order = self.active_orders.get(Side.BID)
        ask_order = self.active_orders.get(Side.ASK)
        self.equity_rows.append(
            {
                "timestamp": timestamp,
                "equity": equity_value,
                "cash": self.account.cash,
                "inventory": self.account.inventory,
                "average_entry_price": self.account.average_entry_price,
                "realized_trading_pnl": self.account.realized_trading_pnl,
                "unrealized_trading_pnl": unrealized,
                "funding_pnl": self.account.funding_pnl,
                "fees": self.account.fees_paid,
                "mid": mid,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "funding_rate": self.latest_funding_rate,
                "bid_quote": None if bid_order is None else bid_order.price,
                "ask_quote": None if ask_order is None else ask_order.price,
                "fair_price": None if decision is None else decision.fair_price,
                "reservation_price": None if decision is None else decision.reservation_price,
                "half_distance": None if decision is None else decision.half_distance,
                "funding_target": None if decision is None else decision.funding_target,
                "pressure": None if decision is None else decision.pressure,
                "strategy_reason": None if decision is None else decision.reason,
                "kill_switch": self.risk.kill_switch_active,
            }
        )

    def _record_mark(self, timestamp: pd.Timestamp | None) -> None:
        if timestamp is None or not self.book.valid:
            return
        self.mark_rows.append(
            {
                "timestamp": timestamp,
                "mid": self.book.mid,
                "best_bid": self.book.best_bid,
                "best_ask": self.book.best_ask,
                "spread": self.book.spread,
            }
        )

    def _current_mid(self, timestamp: pd.Timestamp | None = None) -> float | None:
        if timestamp is not None and self._book_is_stale(timestamp):
            return None
        if self.book.valid:
            return self.book.mid
        return self.previous_mark

    def _liquidation_equity(self) -> float:
        if self.book.valid:
            return self.account.liquidation_adjusted_equity(self.book.best_bid, self.book.best_ask)
        if self.previous_mark is None:
            return self.account.cash + self.account.funding_pnl - self.account.fees_paid
        return self.account.equity(self.previous_mark)

    def _forced_flat_equity(self) -> float:
        slippage_rate = max(0.0, self.config.execution.force_flat_slippage_bps) / 10_000.0
        if self.book.valid:
            if self.account.inventory > 0:
                flatten_price = self.book.best_bid * (1.0 - slippage_rate)
                inventory_value = self.account.inventory * flatten_price
            elif self.account.inventory < 0:
                flatten_price = self.book.best_ask * (1.0 + slippage_rate)
                inventory_value = self.account.inventory * flatten_price
            else:
                inventory_value = 0.0
            return self.account.cash + inventory_value + self.account.funding_pnl - self.account.fees_paid
        if self.previous_mark is None:
            return self.account.cash + self.account.funding_pnl - self.account.fees_paid
        return self.account.equity(self.previous_mark)

    @staticmethod
    def _day_end(timestamp: pd.Timestamp) -> pd.Timestamp:
        day_end_ns = ((timestamp.value // _NS_PER_DAY) + 1) * _NS_PER_DAY
        return pd.Timestamp(day_end_ns, unit="ns", tz="UTC")

    def _in_reduce_only_window(self, timestamp: pd.Timestamp) -> bool:
        day_end_ns = ((timestamp.value // _NS_PER_DAY) + 1) * _NS_PER_DAY
        window_start_ns = day_end_ns - self.config.risk.eod_reduce_window_minutes * 60 * _NS_PER_SECOND
        return timestamp.value >= window_start_ns


_FILL_DIAGNOSTIC_COLUMNS = [
    "timestamp",
    "order_id",
    "side",
    "price",
    "quantity",
    "signed_quantity",
    "trade_price",
    "trade_size",
    "mid_at_fill",
    "best_bid",
    "best_ask",
    "spread_at_fill",
    "queue_ahead_before",
    "queue_ahead_before_fill",
    "queue_ahead_after",
    "queue_ahead_initial",
    "pressure_at_placement",
    "pressure_at_fill",
    "trade_imbalance_at_fill",
    "microprice_at_fill",
    "inventory_before",
    "quote_age_ms",
    "book_age_ms",
    "order_age_ms",
    "fill_model",
    "queue_depletion_fraction",
    "order_status_at_fill",
    "cancel_requested_time",
    "cancel_effective_time",
    "is_pressure_stop_violation",
    "markout_250ms",
    "markout_1s",
    "markout_5s",
    "markout_30s",
    "realized_spread_1s",
    "realized_spread_5s",
    "realized_spread_30s",
]


def _empty_fills_with_diagnostic_columns() -> pd.DataFrame:
    return pd.DataFrame(columns=_FILL_DIAGNOSTIC_COLUMNS)


def _add_fill_markouts(fills: pd.DataFrame, mark_curve: pd.DataFrame, max_mark_lag_ms: float | None = None) -> pd.DataFrame:
    for column in _FILL_DIAGNOSTIC_COLUMNS:
        if column not in fills.columns:
            fills[column] = pd.NA
    if fills.empty or mark_curve.empty:
        return fills
    marks = mark_curve[["timestamp", "mid"]].dropna().sort_values("timestamp").rename(columns={"timestamp": "mark_timestamp"})
    if marks.empty:
        return fills
    enriched = fills.copy()
    enriched["_fill_row"] = range(len(enriched))
    for label, delta in [
        ("250ms", pd.Timedelta(milliseconds=250)),
        ("1s", pd.Timedelta(seconds=1)),
        ("5s", pd.Timedelta(seconds=5)),
        ("30s", pd.Timedelta(seconds=30)),
    ]:
        lookup = enriched[["_fill_row", "timestamp", "side", "price", "mid_at_fill"]].copy()
        lookup["lookup_time"] = lookup["timestamp"] + delta
        aligned = pd.merge_asof(
            lookup.sort_values("lookup_time"),
            marks.assign(lookup_time=marks["mark_timestamp"])[["lookup_time", "mark_timestamp", "mid"]].sort_values("lookup_time"),
            on="lookup_time",
            direction="forward",
        ).set_index("_fill_row")
        if max_mark_lag_ms is not None and max_mark_lag_ms > 0:
            lookup_lag_ms = (aligned["mark_timestamp"] - aligned["lookup_time"]).dt.total_seconds() * 1000.0
            aligned = aligned[lookup_lag_ms <= max_mark_lag_ms]
        markout = aligned["mid"] - aligned["mid_at_fill"]
        enriched.loc[aligned.index, f"markout_{label}"] = markout
        if label != "250ms":
            realized = (aligned["mid"] - aligned["price"]).where(aligned["side"] == "bid", aligned["price"] - aligned["mid"])
            enriched.loc[aligned.index, f"realized_spread_{label}"] = realized
    return enriched.drop(columns=["_fill_row"])


_MAX_NS = 2**63 - 1
_NS_PER_SECOND = 1_000_000_000
_NS_PER_DAY = 86_400 * _NS_PER_SECOND


@dataclass
class _PreparedArrays:
    book_times: object
    bid_prices: object
    bid_quantities: object
    ask_prices: object
    ask_quantities: object
    trade_times: object
    trade_prices: object
    trade_sizes: object
    trade_is_maker_ask: object
    funding_times: object
    funding_rates: object

    @property
    def book_count(self) -> int:
        return len(self.book_times)

    @property
    def trade_count(self) -> int:
        return len(self.trade_times)

    @property
    def funding_count(self) -> int:
        return len(self.funding_times)

    @staticmethod
    def from_market_data(data: MarketData) -> "_PreparedArrays":
        bid_price_columns = [f"bid_price_{i}" for i in LEVELS]
        bid_qty_columns = [f"bid_qty_{i}" for i in LEVELS]
        ask_price_columns = [f"ask_price_{i}" for i in LEVELS]
        ask_qty_columns = [f"ask_qty_{i}" for i in LEVELS]
        return _PreparedArrays(
            book_times=data.orderbook["datetime"].astype("int64").to_numpy(),
            bid_prices=data.orderbook[bid_price_columns].to_numpy(dtype=float, copy=False),
            bid_quantities=data.orderbook[bid_qty_columns].to_numpy(dtype=float, copy=False),
            ask_prices=data.orderbook[ask_price_columns].to_numpy(dtype=float, copy=False),
            ask_quantities=data.orderbook[ask_qty_columns].to_numpy(dtype=float, copy=False),
            trade_times=data.trades["datetime"].astype("int64").to_numpy(),
            trade_prices=data.trades["price"].to_numpy(dtype=float, copy=False),
            trade_sizes=data.trades["size"].to_numpy(dtype=float, copy=False),
            trade_is_maker_ask=data.trades["is_maker_ask"].to_numpy(dtype=int, copy=False),
            funding_times=data.fundings["datetime"].astype("int64").to_numpy(),
            funding_rates=data.fundings["funding_rate"].to_numpy(dtype=float, copy=False),
        )
