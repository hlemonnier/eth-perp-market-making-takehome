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
    queue_ahead_initial: float | None = None
    placement_pressure: float | None = None
    placement_trade_imbalance: float | None = None
    placement_microprice: float | None = None
    last_known_book_time: pd.Timestamp | None = None
    last_visible_queue_ahead: float | None = None
    cancel_requested_time: pd.Timestamp | None = None
    cancel_effective_time: pd.Timestamp | None = None
    cancel_reason: str | None = None
    status: str = "pending_new"

    def __post_init__(self) -> None:
        if self.queue_ahead_initial is None:
            self.queue_ahead_initial = float(self.queue_ahead)
        if self.last_visible_queue_ahead is None:
            self.last_visible_queue_ahead = float(self.queue_ahead)

    @property
    def new_order_time(self) -> pd.Timestamp:
        return self.created_time

    @property
    def exchange_active_time(self) -> pd.Timestamp:
        return self.active_time

    @property
    def order_state(self) -> str:
        return self.status

    def is_active(self, timestamp: pd.Timestamp) -> bool:
        self.refresh_state(timestamp)
        if self.remaining_quantity <= 1e-12 or timestamp < self.active_time:
            return False
        if self.status == "live":
            return True
        if self.status == "pending_cancel" and self.cancel_effective_time is not None:
            return timestamp < self.cancel_effective_time
        return False

    def state_at(self, timestamp: pd.Timestamp) -> str:
        if self.status == "pending_new" and timestamp >= self.active_time:
            return "live"
        if self.status == "live" and timestamp < self.active_time:
            return "pending_new"
        return self.status

    def is_open(self) -> bool:
        return self.status in {"pending_new", "live", "pending_cancel"} and self.remaining_quantity > 1e-12

    def is_cancel_pending(self) -> bool:
        return self.status == "pending_cancel"

    def request_cancel(self, timestamp: pd.Timestamp, effective_time: pd.Timestamp, reason: str) -> None:
        if self.status in {"cancelled", "filled"}:
            return
        self.status = "pending_cancel"
        self.cancel_requested_time = timestamp
        self.cancel_effective_time = effective_time
        self.cancel_reason = reason

    def complete_cancel(self) -> None:
        if self.status == "pending_cancel":
            self.status = "cancelled"

    def refresh_state(self, timestamp: pd.Timestamp) -> None:
        if self.status == "pending_new" and timestamp >= self.active_time:
            self.status = "live"

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
