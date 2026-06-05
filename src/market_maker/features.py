from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import sqrt

import numpy as np
import pandas as pd


@dataclass
class RollingFeatures:
    mid_window_seconds: int
    trade_window_seconds: int = 60
    mids: deque[tuple[pd.Timestamp, float]] = field(default_factory=deque)
    trades: deque[tuple[pd.Timestamp, float, float]] = field(default_factory=deque)
    volatility_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_mid: float | None = None
    last_jump_abs: float = 0.0

    def _evict(self, timestamp: pd.Timestamp) -> None:
        mid_cutoff = timestamp - pd.Timedelta(seconds=self.mid_window_seconds)
        while self.mids and self.mids[0][0] < mid_cutoff:
            self.mids.popleft()
        trade_cutoff = timestamp - pd.Timedelta(seconds=self.trade_window_seconds)
        while self.trades and self.trades[0][0] < trade_cutoff:
            self.trades.popleft()

    def update_mid(self, timestamp: pd.Timestamp, mid: float) -> None:
        self._evict(timestamp)
        self.last_jump_abs = 0.0 if self.last_mid is None else abs(mid - self.last_mid)
        self.last_mid = mid
        self.mids.append((timestamp, mid))

    def update_trade(self, timestamp: pd.Timestamp, is_maker_ask: int, size: float) -> None:
        self._evict(timestamp)
        sign = 1.0 if int(is_maker_ask) == 1 else -1.0
        self.trades.append((timestamp, sign, float(size)))

    def volatility_abs(self) -> float:
        if len(self.mids) < 3:
            return 0.0
        values = np.array([mid for _, mid in self.mids], dtype=float)
        return float(np.std(np.diff(values), ddof=1))

    def volatility_buffer(self, quote_horizon_seconds: float, k_vol: float) -> float:
        vol = self.volatility_abs()
        if vol > 0:
            self.volatility_history.append(vol)
        if vol <= 0:
            return 0.0
        return float(k_vol * vol * sqrt(max(quote_horizon_seconds, 1.0)))

    def high_volatility(self) -> bool:
        if len(self.volatility_history) < 50:
            return False
        current = self.volatility_abs()
        threshold = float(np.quantile(np.array(self.volatility_history), 0.95))
        return current > threshold > 0

    def trade_imbalance(self) -> float:
        total = sum(size for _, _, size in self.trades)
        if total <= 0:
            return 0.0
        signed = sum(sign * size for _, sign, size in self.trades)
        return float(np.clip(signed / total, -1.0, 1.0))
