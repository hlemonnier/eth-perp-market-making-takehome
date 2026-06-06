from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, tanh

import pandas as pd

from market_maker.accounting import AccountingState
from market_maker.book_state import BookState
from market_maker.config import RiskConfig, StrategyConfig
from market_maker.features import RollingFeatures
from market_maker.risk import RiskState, clip_quote_sizes, is_reduce_only_window


@dataclass(frozen=True)
class QuoteDecision:
    bid_price: float | None
    bid_size: float
    ask_price: float | None
    ask_size: float
    fair_price: float | None
    reservation_price: float | None
    half_distance: float | None
    funding_target: float
    pressure: float
    reason: str


def floor_to_tick(price: float, tick: float) -> float:
    decimals = _price_decimals_from_tick(tick)
    ticks = floor(price / tick + 1e-9)
    return round(ticks * tick, decimals)


def ceil_to_tick(price: float, tick: float) -> float:
    decimals = _price_decimals_from_tick(tick)
    ticks = ceil(price / tick - 1e-9)
    return round(ticks * tick, decimals)


def _price_decimals_from_tick(tick: float) -> int:
    text = f"{tick:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".")[1])


class MarketMakingStrategy:
    def __init__(self, config: StrategyConfig, risk_config: RiskConfig, tick_size: float):
        self.config = config
        self.risk_config = risk_config
        self.tick_size = tick_size

    def quote(
        self,
        timestamp: pd.Timestamp,
        book: BookState,
        account: AccountingState,
        features: RollingFeatures,
        latest_funding_rate: float,
        risk: RiskState,
        day_end: pd.Timestamp,
    ) -> QuoteDecision:
        if not book.valid:
            return self._empty("invalid_book")
        if risk.kill_switch_active:
            return self._empty("kill_switch")
        if risk.in_cooldown(timestamp):
            return self._empty("cooldown")
        spread_ticks = int(round(book.spread / self.tick_size))
        if spread_ticks < self.risk_config.min_economic_spread_ticks:
            return self._empty("uneconomic_spread")

        cfg = self.config
        trade_imbalance = features.trade_imbalance()
        fair = book.mid + cfg.alpha_micro * (book.microprice - book.mid) + cfg.alpha_flow * book.half_spread * trade_imbalance
        funding_z = tanh(latest_funding_rate / cfg.funding_scale) if cfg.funding_scale else 0.0
        q_target = max(-cfg.q_max / 2.0, min(cfg.q_max / 2.0, -cfg.funding_target_frac * cfg.q_max * funding_z))

        vol_buffer = features.volatility_buffer(cfg.quote_horizon_seconds, cfg.k_vol)
        delta = max(cfg.min_half_spread_ticks * self.tick_size, cfg.spread_mult * book.half_spread, vol_buffer)
        if features.high_volatility():
            delta *= self.risk_config.vol_widen_multiplier
        if features.last_jump_abs >= self.risk_config.jump_ticks_stop * self.tick_size:
            risk.start_cooldown(timestamp)
            return self._empty("jump_cooldown")

        reservation = fair - cfg.theta_inv * delta * (account.inventory - q_target) / cfg.q_max
        pressure = cfg.w_book * book.top_imbalance + cfg.w_trade * trade_imbalance
        bid_delta = delta * (1.0 + cfg.k_adv * max(0.0, -pressure))
        ask_delta = delta * (1.0 + cfg.k_adv * max(0.0, pressure))
        raw_bid = reservation - bid_delta
        raw_ask = reservation + ask_delta

        bid_price = min(floor_to_tick(raw_bid, self.tick_size), book.best_ask - self.tick_size)
        ask_price = max(ceil_to_tick(raw_ask, self.tick_size), book.best_bid + self.tick_size)
        bid_size, ask_size = clip_quote_sizes(account.inventory, q_target, cfg)

        if pressure < -cfg.pressure_stop:
            bid_size = 0.0
        if pressure > cfg.pressure_stop:
            ask_size = 0.0

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

        return QuoteDecision(
            bid_price=bid_price if bid_size > 1e-12 else None,
            bid_size=bid_size,
            ask_price=ask_price if ask_size > 1e-12 else None,
            ask_size=ask_size,
            fair_price=fair,
            reservation_price=reservation,
            half_distance=delta,
            funding_target=q_target,
            pressure=pressure,
            reason="ok",
        )

    @staticmethod
    def _empty(reason: str) -> QuoteDecision:
        return QuoteDecision(
            bid_price=None,
            bid_size=0.0,
            ask_price=None,
            ask_size=0.0,
            fair_price=None,
            reservation_price=None,
            half_distance=None,
            funding_target=0.0,
            pressure=0.0,
            reason=reason,
        )
