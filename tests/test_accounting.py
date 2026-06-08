import pandas as pd
import pytest

from market_maker.accounting import AccountingState
from market_maker.orders import Fill, Side


def fill(side: Side, price: float, quantity: float) -> Fill:
    return Fill(
        timestamp=pd.Timestamp("2026-03-19T00:00:00Z"),
        order_id=1,
        side=side,
        price=price,
        quantity=quantity,
        trade_price=price,
        trade_size=quantity,
        queue_ahead_before=0.0,
        queue_ahead_after=0.0,
    )


def test_long_position_realized_and_mtm_pnl():
    account = AccountingState()
    account.apply_fill(fill(Side.BID, 100.0, 1.0))
    assert account.cash == pytest.approx(-100.0)
    assert account.inventory == pytest.approx(1.0)
    assert account.equity(102.0) == pytest.approx(2.0)

    account.apply_fill(fill(Side.ASK, 103.0, 1.0))
    assert account.cash == pytest.approx(3.0)
    assert account.inventory == pytest.approx(0.0)
    assert account.realized_trading_pnl == pytest.approx(3.0)
    assert account.equity(103.0) == pytest.approx(3.0)


def test_short_position_realized_and_unrealized_pnl():
    account = AccountingState()
    account.apply_fill(fill(Side.ASK, 100.0, 2.0))
    account.apply_fill(fill(Side.BID, 95.0, 1.0))
    assert account.cash == pytest.approx(105.0)
    assert account.inventory == pytest.approx(-1.0)
    assert account.realized_trading_pnl == pytest.approx(5.0)
    assert account.unrealized_trading_pnl(90.0) == pytest.approx(10.0)
    assert account.equity(90.0) == pytest.approx(15.0)


def test_fee_reduces_equity():
    account = AccountingState(maker_fee_bps=1.0)
    account.apply_fill(fill(Side.BID, 100.0, 1.0))
    assert account.fees_paid == pytest.approx(0.01)
    assert account.equity(100.0) == pytest.approx(-0.01)


def test_funding_pnl_long_and_short():
    long_account = AccountingState(inventory=1.0)
    short_account = AccountingState(inventory=-1.0)
    assert long_account.accrue_funding(3600, 2000.0, 0.0001, 8.0) == pytest.approx(-0.025)
    assert short_account.accrue_funding(3600, 2000.0, 0.0001, 8.0) == pytest.approx(0.025)


def test_funding_accrual_accumulates_rate_changes_over_intervals():
    account = AccountingState(inventory=2.0)

    first = account.accrue_funding(3600, 2000.0, 0.0001, 8.0)
    second = account.accrue_funding(7200, 2100.0, -0.0002, 8.0)

    assert first == pytest.approx(-0.05)
    assert second == pytest.approx(0.21)
    assert account.funding_pnl == pytest.approx(0.16)


def test_mark_to_market_example():
    account = AccountingState(cash=-1000.0, inventory=0.5, average_entry_price=2000.0)
    assert account.equity(2100.0) == pytest.approx(50.0)
    assert account.equity(2080.0) == pytest.approx(40.0)
