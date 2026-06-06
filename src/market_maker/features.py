from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import sqrt

import pandas as pd


@dataclass
class RollingFeatures:
    mid_window_seconds: int
    trade_window_seconds: int = 60
    mids: deque[tuple[pd.Timestamp, float]] = field(default_factory=deque)
    trades: deque[tuple[pd.Timestamp, float, float]] = field(default_factory=deque)
    normalized_mid_changes: deque[tuple[pd.Timestamp, float]] = field(default_factory=deque)
    volatility_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_mid: float | None = None
    last_mid_timestamp: pd.Timestamp | None = None
    last_jump_abs: float = 0.0
    current_volatility_abs: float = 0.0
    volatility_sum: float = 0.0
    volatility_sumsq: float = 0.0
    volatility_history_updates: int = 0
    volatility_threshold_95: float = 0.0

    def _evict(self, timestamp: pd.Timestamp) -> bool:
        mid_cutoff_ns = timestamp.value - self.mid_window_seconds * 1_000_000_000
        while self.mids and self.mids[0][0].value < mid_cutoff_ns:
            self.mids.popleft()
        evicted_mid_change = False
        while self.normalized_mid_changes and self.normalized_mid_changes[0][0].value < mid_cutoff_ns:
            _, change = self.normalized_mid_changes.popleft()
            self.volatility_sum -= change
            self.volatility_sumsq -= change * change
            evicted_mid_change = True
        trade_cutoff_ns = timestamp.value - self.trade_window_seconds * 1_000_000_000
        while self.trades and self.trades[0][0].value < trade_cutoff_ns:
            self.trades.popleft()
        return evicted_mid_change

    def update_mid(self, timestamp: pd.Timestamp, mid: float) -> None:
        evicted_mid_change = self._evict(timestamp)
        if self.last_mid is None or self.last_mid_timestamp is None:
            self.last_jump_abs = 0.0
            if evicted_mid_change:
                self.current_volatility_abs = self._compute_volatility_abs()
        else:
            self.last_jump_abs = abs(mid - self.last_mid)
            elapsed = max((timestamp.value - self.last_mid_timestamp.value) / 1_000_000_000.0, 1e-6)
            change = (mid - self.last_mid) / sqrt(elapsed)
            self.normalized_mid_changes.append((timestamp, change))
            self.volatility_sum += change
            self.volatility_sumsq += change * change
            self.current_volatility_abs = self._compute_volatility_abs()
            vol = self.current_volatility_abs
            if vol > 0:
                self._append_volatility_history(vol)
        self.last_mid = mid
        self.last_mid_timestamp = timestamp
        self.mids.append((timestamp, mid))

    def update_trade(self, timestamp: pd.Timestamp, is_maker_ask: int, size: float) -> None:
        evicted_mid_change = self._evict(timestamp)
        if evicted_mid_change:
            self.current_volatility_abs = self._compute_volatility_abs()
        sign = 1.0 if int(is_maker_ask) == 1 else -1.0
        self.trades.append((timestamp, sign, float(size)))

    def volatility_abs(self) -> float:
        return self.current_volatility_abs

    def _compute_volatility_abs(self) -> float:
        count = len(self.normalized_mid_changes)
        if count < 2:
            return 0.0
        variance = (self.volatility_sumsq - self.volatility_sum * self.volatility_sum / count) / (count - 1)
        return sqrt(max(variance, 0.0))

    def volatility_buffer(self, quote_horizon_seconds: float, k_vol: float) -> float:
        vol = self.volatility_abs()
        if vol <= 0:
            return 0.0
        return float(k_vol * vol * sqrt(max(quote_horizon_seconds, 1e-6)))

    def high_volatility(self) -> bool:
        if len(self.volatility_history) < 50:
            return False
        current = self.volatility_abs()
        return current > self.volatility_threshold_95 > 0

    def _append_volatility_history(self, vol: float) -> None:
        self.volatility_history.append(vol)
        self.volatility_history_updates += 1
        if len(self.volatility_history) < 50:
            return
        if len(self.volatility_history) < self.volatility_history.maxlen or self.volatility_history_updates % 50 == 0:
            values = sorted(self.volatility_history)
            index = int(0.95 * (len(values) - 1))
            self.volatility_threshold_95 = values[index]

    def trade_imbalance(self) -> float:
        total = sum(size for _, _, size in self.trades)
        if total <= 0:
            return 0.0
        signed = sum(sign * size for _, sign, size in self.trades)
        return max(-1.0, min(1.0, signed / total))
