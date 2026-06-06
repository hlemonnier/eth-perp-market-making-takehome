import pandas as pd
import pytest

from market_maker.accounting import AccountingState
from market_maker.book_state import BookState
from market_maker.config import RiskConfig, StrategyConfig
from market_maker.features import RollingFeatures
from market_maker.metrics import daily_summary
from market_maker.risk import RiskState, clip_quote_sizes
from market_maker.strategy import MarketMakingStrategy, ceil_to_tick, floor_to_tick


def strategy_config() -> StrategyConfig:
    return StrategyConfig(
        alpha_micro=0.5,
        alpha_flow=0.25,
        funding_scale=0.0001,
        funding_target_frac=0.25,
        theta_inv=1.5,
        base_order_size_eth=0.10,
        q_max=1.0,
        max_quote_size_eth=0.20,
        min_half_spread_ticks=2,
        spread_mult=1.0,
        vol_window_seconds=60,
        quote_horizon_seconds=5,
        k_vol=1.0,
        k_adv=0.5,
        pressure_stop=0.85,
        w_book=0.5,
        w_trade=0.5,
        refresh_interval_seconds=5,
        max_quote_age_seconds=10,
        requote_bbo_ticks=1,
        requote_delta_ticks=2,
        funding_retarget_threshold=0.05,
    )


def risk_config() -> RiskConfig:
    return RiskConfig(
        max_drawdown_usd=100.0,
        vol_widen_multiplier=2.0,
        jump_ticks_stop=10,
        cooldown_seconds=10,
        eod_reduce_window_minutes=15,
        min_economic_spread_ticks=1,
    )


def valid_book() -> BookState:
    row = {"datetime": pd.Timestamp("2026-03-19T00:00:00Z")}
    for level in range(1, 21):
        row[f"bid_price_{level}"] = 100.0 - level
        row[f"ask_price_{level}"] = 100.0 + level
        row[f"bid_qty_{level}"] = 1.0
        row[f"ask_qty_{level}"] = 1.0
    book = BookState()
    assert book.update_from_row(pd.Series(row))
    return book


def test_inventory_limit_clips_bid_size():
    bid_size, ask_size = clip_quote_sizes(0.95, 0.95, strategy_config())
    assert bid_size == pytest.approx(0.05)
    assert ask_size > 0
    bid_size, _ = clip_quote_sizes(1.0, 0.0, strategy_config())
    assert bid_size == pytest.approx(0.0)


def test_strategy_uses_only_current_feature_state():
    cfg = strategy_config()
    risk = RiskState(risk_config())
    strategy = MarketMakingStrategy(cfg, risk_config(), tick_size=1.0)
    features = RollingFeatures(mid_window_seconds=60)
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    book = valid_book()

    decision_without_future = strategy.quote(timestamp, book, AccountingState(), features, 0.0, risk, timestamp + pd.Timedelta(days=1))
    # A future trade is intentionally not added to features; quote must remain unchanged.
    decision_with_future_rows_present_but_not_processed = strategy.quote(timestamp, book, AccountingState(), features, 0.0, risk, timestamp + pd.Timedelta(days=1))

    assert decision_without_future.bid_price == decision_with_future_rows_present_but_not_processed.bid_price
    assert decision_without_future.ask_price == decision_with_future_rows_present_but_not_processed.ask_price


def test_tick_rounding_does_not_slip_one_tick_on_float_boundaries():
    assert floor_to_tick(100.3, 0.1) == pytest.approx(100.3)
    assert ceil_to_tick(100.1, 0.1) == pytest.approx(100.1)
    assert floor_to_tick(100.29999999999998, 0.1) == pytest.approx(100.3)
    assert ceil_to_tick(100.10000000000001, 0.1) == pytest.approx(100.1)


def test_one_tick_float_spread_is_not_rejected_as_uneconomic():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    bids = [(100.0 - (level - 1) * 0.1, 1.0) for level in range(1, 21)]
    asks = [(100.09999999999991 + (level - 1) * 0.1, 1.0) for level in range(1, 21)]
    book = BookState()
    assert book.update(timestamp, bids, asks)
    strategy = MarketMakingStrategy(strategy_config(), risk_config(), tick_size=0.1)

    decision = strategy.quote(
        timestamp,
        book,
        AccountingState(),
        RollingFeatures(mid_window_seconds=60),
        0.0,
        RiskState(risk_config()),
        timestamp + pd.Timedelta(days=1),
    )

    assert decision.reason == "ok"


def test_eod_reduce_only_caps_size_and_blocks_flat_inventory():
    cfg = strategy_config()
    risk_cfg = risk_config()
    strategy = MarketMakingStrategy(cfg, risk_cfg, tick_size=1.0)
    features = RollingFeatures(mid_window_seconds=60)
    timestamp = pd.Timestamp("2026-03-19T23:50:00Z")
    day_end = pd.Timestamp("2026-03-20T00:00:00Z")
    book = valid_book()

    long_decision = strategy.quote(
        timestamp,
        book,
        AccountingState(inventory=0.03, average_entry_price=100.0),
        features,
        0.0,
        RiskState(risk_cfg),
        day_end,
    )
    assert long_decision.bid_price is None
    assert long_decision.bid_size == pytest.approx(0.0)
    assert long_decision.ask_size == pytest.approx(0.03)

    short_decision = strategy.quote(
        timestamp,
        book,
        AccountingState(inventory=-0.04, average_entry_price=100.0),
        features,
        0.0,
        RiskState(risk_cfg),
        day_end,
    )
    assert short_decision.ask_price is None
    assert short_decision.ask_size == pytest.approx(0.0)
    assert short_decision.bid_size == pytest.approx(0.04)

    flat_decision = strategy.quote(timestamp, book, AccountingState(), features, 0.0, RiskState(risk_cfg), day_end)
    assert flat_decision.bid_price is None
    assert flat_decision.ask_price is None
    assert flat_decision.bid_size == pytest.approx(0.0)
    assert flat_decision.ask_size == pytest.approx(0.0)


def test_daily_aggregation_carries_equity():
    equity = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-03-19T23:59:00Z", "2026-03-20T23:59:00Z", "2026-03-21T23:59:00Z"],
                utc=True,
            ),
            "equity": [100.0, 130.0, 120.0],
            "realized_trading_pnl": [100.0, 130.0, 120.0],
            "unrealized_trading_pnl": [0.0, 0.0, 0.0],
            "funding_pnl": [0.0, 0.0, 0.0],
            "fees": [0.0, 0.0, 0.0],
            "inventory": [0.0, 0.0, 0.0],
        }
    )
    daily = daily_summary(equity, pd.DataFrame())
    assert daily["daily_pnl"].tolist() == pytest.approx([100.0, 30.0, -10.0])


def test_daily_aggregation_reports_incremental_pnl_components():
    equity = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-03-19T23:59:00Z", "2026-03-20T23:59:00Z", "2026-03-21T23:59:00Z"],
                utc=True,
            ),
            "equity": [15.9, 19.6, 17.1],
            "realized_trading_pnl": [10.0, 15.0, 12.0],
            "unrealized_trading_pnl": [5.0, 3.0, 4.0],
            "funding_pnl": [1.0, 2.0, 1.5],
            "fees": [0.1, 0.4, 0.4],
            "inventory": [0.0, 0.0, 0.0],
        }
    )

    daily = daily_summary(equity, pd.DataFrame())

    assert daily["daily_realized_trading_pnl"].tolist() == pytest.approx([10.0, 5.0, -3.0])
    assert daily["daily_unrealized_trading_pnl_change"].tolist() == pytest.approx([5.0, -2.0, 1.0])
    assert daily["daily_funding_pnl"].tolist() == pytest.approx([1.0, 1.0, -0.5])
    assert daily["daily_fees"].tolist() == pytest.approx([0.1, 0.3, 0.0])


def test_bad_book_is_invalid():
    row = {"datetime": pd.Timestamp("2026-03-19T00:00:00Z")}
    for level in range(1, 21):
        row[f"bid_price_{level}"] = 101.0 - level * 0.01
        row[f"ask_price_{level}"] = 100.0 + level * 0.01
        row[f"bid_qty_{level}"] = 1.0
        row[f"ask_qty_{level}"] = 1.0
    book = BookState()
    assert not book.update_from_row(pd.Series(row))
    assert book.invalid_reason == "locked or crossed book"
