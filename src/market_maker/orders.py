from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"

    @property
    def signed_fill_multiplier(self) -> float:
        return 1.0 if self is Side.BID else -1.0


@dataclass
class LiveOrder:
    order_id: int
    side: Side
    price: float
    original_quantity: float
    remaining_quantity: float
    created_time: pd.Timestamp
    active_time: pd.Timestamp
    queue_ahead: float = 0.0
    status: str = "live"

    def is_active(self, timestamp: pd.Timestamp) -> bool:
        return self.status == "live" and self.remaining_quantity > 1e-12 and timestamp >= self.active_time

    def reduce(self, quantity: float) -> None:
        self.remaining_quantity = max(0.0, self.remaining_quantity - quantity)
        if self.remaining_quantity <= 1e-12:
            self.status = "filled"


@dataclass(frozen=True)
class Fill:
    timestamp: pd.Timestamp
    order_id: int
    side: Side
    price: float
    quantity: float
    trade_price: float
    trade_size: float
    queue_ahead_before: float
    queue_ahead_after: float
    mid_at_fill: float | None = None

    @property
    def signed_quantity(self) -> float:
        return self.side.signed_fill_multiplier * self.quantity

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.price)
