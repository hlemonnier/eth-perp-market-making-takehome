import pandas as pd
import pytest

from market_maker.fill_model import FillModel, TradeEvent
from market_maker.orders import LiveOrder, Side


def live_order(side: Side, price: float, quantity: float, queue_ahead: float = 0.0) -> LiveOrder:
    created = pd.Timestamp("2026-03-19T00:00:00Z")
    return LiveOrder(
        order_id=1,
        side=side,
        price=price,
        original_quantity=quantity,
        remaining_quantity=quantity,
        created_time=created,
        active_time=created + pd.Timedelta(milliseconds=1),
        queue_ahead=queue_ahead,
    )


def trade(price: float, size: float, is_maker_ask: int) -> TradeEvent:
    return TradeEvent(
        timestamp=pd.Timestamp("2026-03-19T00:00:01Z"),
        price=price,
        size=size,
        is_maker_ask=is_maker_ask,
    )


def test_simple_bid_partial_and_completion():
    model = FillModel("simple")
    order = live_order(Side.BID, 99.0, 1.0)
    first = model.process_trade(order, trade(99.0, 0.4, 0))
    assert first is not None
    assert first.quantity == pytest.approx(0.4)
    assert order.remaining_quantity == pytest.approx(0.6)

    second = model.process_trade(order, trade(98.5, 1.0, 0))
    assert second is not None
    assert second.quantity == pytest.approx(0.6)
    assert order.status == "filled"


def test_trade_direction_prevents_wrong_side_fill():
    model = FillModel("simple")
    order = live_order(Side.BID, 99.0, 1.0)
    assert model.process_trade(order, trade(101.0, 10.0, 1)) is None
    assert order.remaining_quantity == pytest.approx(1.0)


def test_conservative_queue_consumes_ahead_before_fill():
    model = FillModel("conservative_queue")
    order = live_order(Side.BID, 99.0, 1.0, queue_ahead=5.0)
    assert model.process_trade(order, trade(99.0, 3.0, 0)) is None
    assert order.queue_ahead == pytest.approx(2.0)
    assert order.remaining_quantity == pytest.approx(1.0)

    fill = model.process_trade(order, trade(99.0, 4.0, 0))
    assert fill is not None
    assert fill.quantity == pytest.approx(1.0)
    assert order.status == "filled"


def test_order_not_active_at_same_timestamp():
    model = FillModel("simple")
    created = pd.Timestamp("2026-03-19T00:00:00Z")
    order = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=created,
        active_time=created + pd.Timedelta(milliseconds=250),
    )
    same_time_trade = TradeEvent(timestamp=created, price=99.0, size=1.0, is_maker_ask=0)
    assert model.process_trade(order, same_time_trade) is None
