from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from market_maker.orders import Side


LEVELS = range(1, 21)


@dataclass
class BookState:
    timestamp: pd.Timestamp | None = None
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    bid_prices_array: np.ndarray | None = None
    bid_quantities_array: np.ndarray | None = None
    ask_prices_array: np.ndarray | None = None
    ask_quantities_array: np.ndarray | None = None
    valid: bool = False
    invalid_reason: str | None = None

    def update_from_row(self, row: pd.Series) -> bool:
        bids = [(float(row[f"bid_price_{i}"]), float(row[f"bid_qty_{i}"])) for i in LEVELS]
        asks = [(float(row[f"ask_price_{i}"]), float(row[f"ask_qty_{i}"])) for i in LEVELS]
        self.timestamp = pd.Timestamp(row["datetime"])
        return self.update(timestamp=self.timestamp, bids=bids, asks=asks)

    def update_from_arrays(
        self,
        timestamp: pd.Timestamp,
        bid_prices: np.ndarray,
        bid_quantities: np.ndarray,
        ask_prices: np.ndarray,
        ask_quantities: np.ndarray,
    ) -> bool:
        bids = list(zip(bid_prices.astype(float).tolist(), bid_quantities.astype(float).tolist()))
        asks = list(zip(ask_prices.astype(float).tolist(), ask_quantities.astype(float).tolist()))
        return self.update(timestamp=timestamp, bids=bids, asks=asks)

    def update(self, timestamp: pd.Timestamp, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> bool:
        self.timestamp = timestamp
        self.bids = bids
        self.asks = asks
        self.bid_prices_array = np.array([px for px, _ in bids], dtype=float)
        self.bid_quantities_array = np.array([qty for _, qty in bids], dtype=float)
        self.ask_prices_array = np.array([px for px, _ in asks], dtype=float)
        self.ask_quantities_array = np.array([qty for _, qty in asks], dtype=float)
        self.valid, self.invalid_reason = self._validate()
        return self.valid

    def fast_update_from_arrays(
        self,
        timestamp: pd.Timestamp,
        bid_prices: np.ndarray,
        bid_quantities: np.ndarray,
        ask_prices: np.ndarray,
        ask_quantities: np.ndarray,
    ) -> bool:
        self.timestamp = timestamp
        self.bid_prices_array = bid_prices
        self.bid_quantities_array = bid_quantities
        self.ask_prices_array = ask_prices
        self.ask_quantities_array = ask_quantities
        self.bids = []
        self.asks = []
        self.valid, self.invalid_reason = self._validate()
        return self.valid

    def _validate(self) -> tuple[bool, str | None]:
        if self.bid_prices_array is None or self.ask_prices_array is None:
            return False, "missing book sides"
        bid_prices = self.bid_prices_array
        ask_prices = self.ask_prices_array
        bid_qty = self.bid_quantities_array
        ask_qty = self.ask_quantities_array
        if not np.isfinite(bid_prices).all() or not np.isfinite(ask_prices).all():
            return False, "non-finite prices"
        if not np.isfinite(bid_qty).all() or not np.isfinite(ask_qty).all():
            return False, "non-finite quantities"
        if (bid_prices <= 0).any() or (ask_prices <= 0).any():
            return False, "non-positive prices"
        if (bid_qty < 0).any() or (ask_qty < 0).any():
            return False, "negative quantities"
        if not np.all(bid_prices[:-1] >= bid_prices[1:]):
            return False, "bid prices not monotone"
        if not np.all(ask_prices[:-1] <= ask_prices[1:]):
            return False, "ask prices not monotone"
        if self.best_bid >= self.best_ask:
            return False, "locked or crossed book"
        return True, None

    @property
    def best_bid(self) -> float:
        return float(self.bid_prices_array[0])

    @property
    def best_ask(self) -> float:
        return float(self.ask_prices_array[0])

    @property
    def best_bid_qty(self) -> float:
        return float(self.bid_quantities_array[0])

    @property
    def best_ask_qty(self) -> float:
        return float(self.ask_quantities_array[0])

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid

    @property
    def half_spread(self) -> float:
        return self.spread / 2.0

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def microprice(self) -> float:
        denom = self.best_bid_qty + self.best_ask_qty
        if denom <= 0:
            return self.mid
        return (self.best_ask * self.best_bid_qty + self.best_bid * self.best_ask_qty) / denom

    @property
    def top_imbalance(self) -> float:
        denom = self.best_bid_qty + self.best_ask_qty
        if denom <= 0:
            return 0.0
        return (self.best_bid_qty - self.best_ask_qty) / denom

    def depth(self, levels: int = 20, side: Side | None = None) -> float:
        bid_depth = float(np.sum(self.bid_quantities_array[:levels]))
        ask_depth = float(np.sum(self.ask_quantities_array[:levels]))
        if side is Side.BID:
            return bid_depth
        if side is Side.ASK:
            return ask_depth
        return bid_depth + ask_depth

    def notional_depth(self, levels: int = 20, side: Side | None = None) -> float:
        bid_depth = float(np.sum(self.bid_prices_array[:levels] * self.bid_quantities_array[:levels]))
        ask_depth = float(np.sum(self.ask_prices_array[:levels] * self.ask_quantities_array[:levels]))
        if side is Side.BID:
            return bid_depth
        if side is Side.ASK:
            return ask_depth
        return bid_depth + ask_depth

    def queue_ahead(self, side: Side, price: float) -> float:
        if side is Side.BID:
            if price > self.best_bid:
                return 0.0
            return float(np.sum(self.bid_quantities_array[self.bid_prices_array >= price]))
        if price < self.best_ask:
            return 0.0
        return float(np.sum(self.ask_quantities_array[self.ask_prices_array <= price]))
