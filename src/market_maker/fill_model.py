from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_maker.orders import Fill, LiveOrder, Side


@dataclass(frozen=True)
class TradeEvent:
    timestamp: pd.Timestamp
    price: float
    size: float
    is_maker_ask: int


def trade_reaches_order(order: LiveOrder, trade: TradeEvent) -> bool:
    if not order.is_active(trade.timestamp):
        return False
    if trade.size <= 0:
        return False
    if order.side is Side.ASK:
        return trade.is_maker_ask == 1 and trade.price >= order.price
    return trade.is_maker_ask == 0 and trade.price <= order.price


class FillModel:
    def __init__(self, name: str = "conservative_queue", queue_depletion_fraction: float = 0.0):
        if name not in {"simple", "conservative_queue", "partial_queue", "calibrated_queue"}:
            raise ValueError(f"Unknown fill model: {name}")
        self.name = name
        self.queue_depletion_fraction = max(0.0, min(1.0, float(queue_depletion_fraction)))

    def process_trade(
        self,
        order: LiveOrder | None,
        trade: TradeEvent,
        mid_at_fill: float | None = None,
    ) -> Fill | None:
        if order is None or not trade_reaches_order(order, trade):
            return None

        queue_before = order.queue_ahead
        eligible_size = trade.size
        if self.name in {"conservative_queue", "partial_queue", "calibrated_queue"} and order.queue_ahead > 0:
            consumed_ahead = min(order.queue_ahead, eligible_size)
            order.queue_ahead = max(0.0, order.queue_ahead - consumed_ahead)
            eligible_size -= consumed_ahead

        fill_qty = min(order.remaining_quantity, eligible_size)
        if fill_qty <= 1e-12:
            return None

        order.reduce(fill_qty)
        return Fill(
            timestamp=trade.timestamp,
            order_id=order.order_id,
            side=order.side,
            price=order.price,
            quantity=fill_qty,
            trade_price=trade.price,
            trade_size=trade.size,
            queue_ahead_before=queue_before,
            queue_ahead_after=order.queue_ahead,
            mid_at_fill=mid_at_fill,
        )
