from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_maker.config import RiskConfig, StrategyConfig


@dataclass
class RiskState:
    config: RiskConfig
    peak_equity: float = 0.0
    kill_switch_active: bool = False
    cooldown_until: pd.Timestamp | None = None

    def update_drawdown(self, timestamp: pd.Timestamp, equity: float) -> None:
        self.peak_equity = max(self.peak_equity, equity)
        if equity - self.peak_equity <= -self.config.max_drawdown_usd:
            self.kill_switch_active = True

    def start_cooldown(self, timestamp: pd.Timestamp) -> None:
        until = timestamp + pd.Timedelta(seconds=self.config.cooldown_seconds)
        if self.cooldown_until is None or until > self.cooldown_until:
            self.cooldown_until = until

    def in_cooldown(self, timestamp: pd.Timestamp) -> bool:
        return self.cooldown_until is not None and timestamp < self.cooldown_until


def clip_quote_sizes(
    inventory: float,
    target_inventory: float,
    strategy: StrategyConfig,
) -> tuple[float, float]:
    q_max = strategy.q_max
    if q_max <= 0:
        return 0.0, 0.0
    x = (inventory - target_inventory) / q_max
    bid_size = strategy.base_order_size_eth * min(max(1.0 - x, 0.0), 2.0)
    ask_size = strategy.base_order_size_eth * min(max(1.0 + x, 0.0), 2.0)
    bid_size = min(bid_size, strategy.max_quote_size_eth, max(0.0, q_max - inventory))
    ask_size = min(ask_size, strategy.max_quote_size_eth, max(0.0, q_max + inventory))
    return max(0.0, bid_size), max(0.0, ask_size)


def is_reduce_only_window(timestamp: pd.Timestamp, day_end: pd.Timestamp, minutes: int) -> bool:
    return timestamp >= day_end - pd.Timedelta(minutes=minutes)
