from __future__ import annotations

import pandas as pd
import pytest

from market_maker.accounting import AccountingState
from market_maker.book_state import BookState
from market_maker.config import AuditConfig, BacktestConfig, DataConfig, ExecutionConfig, RiskConfig, StrategyConfig
from market_maker.data_audit import AuditResult, run_audit
from market_maker.data_loader import MarketData
from market_maker.features import RollingFeatures
from market_maker.metrics import MetricsBundle, daily_summary
from market_maker.orders import LiveOrder, Side
from market_maker.reporting import build_markdown_report
from market_maker.simulator import BacktestResult, Simulator
from market_maker.strategy import MarketMakingStrategy, ceil_to_tick, floor_to_tick


def _config(
    *,
    fill_model: str = "simple",
    report_frequency: str = "1min",
    refresh_interval_seconds: int = 60,
    max_drawdown_usd: float = 1_000.0,
    eod_reduce_window_minutes: int = 0,
) -> BacktestConfig:
    return BacktestConfig(
        data=DataConfig(data_dir="data", days=("2026-03-19",)),
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=0,
            fill_model=fill_model,
            funding_period_hours=8.0,
            report_frequency=report_frequency,
        ),
        strategy=StrategyConfig(
            alpha_micro=0.0,
            alpha_flow=0.0,
            funding_scale=0.0001,
            funding_target_frac=0.0,
            theta_inv=0.0,
            base_order_size_eth=1.0,
            q_max=1.0,
            max_quote_size_eth=1.0,
            min_half_spread_ticks=1,
            spread_mult=0.0,
            vol_window_seconds=60,
            quote_horizon_seconds=5,
            k_vol=0.0,
            k_adv=0.0,
            pressure_stop=1.0,
            w_book=0.0,
            w_trade=0.0,
            refresh_interval_seconds=refresh_interval_seconds,
            max_quote_age_seconds=600,
            requote_bbo_ticks=100,
            requote_delta_ticks=1,
            funding_retarget_threshold=1.0,
        ),
        risk=RiskConfig(
            max_drawdown_usd=max_drawdown_usd,
            vol_widen_multiplier=2.0,
            jump_ticks_stop=100,
            cooldown_seconds=10,
            eod_reduce_window_minutes=eod_reduce_window_minutes,
            min_economic_spread_ticks=1,
        ),
        audit=AuditConfig(
            max_funding_staleness_seconds=120,
            trade_alignment_tolerance_ticks=2,
            tick_sample_size=100,
        ),
    )


def _book_row(timestamp: str, bid: float = 99.0, ask: float = 101.0, *, row_id: int = 0) -> dict[str, object]:
    row: dict[str, object] = {
        "datetime": pd.Timestamp(timestamp),
        "_source_day": "2026-03-19",
        "_row_id": row_id,
    }
    for level in range(1, 21):
        row[f"bid_price_{level}"] = bid - (level - 1)
        row[f"ask_price_{level}"] = ask + (level - 1)
        row[f"bid_qty_{level}"] = 10.0
        row[f"ask_qty_{level}"] = 10.0
    return row


def _book_state(bid: float = 99.0, ask: float = 101.0) -> BookState:
    book = BookState()
    assert book.update_from_row(pd.Series(_book_row("2026-03-19T00:00:00Z", bid, ask)))
    return book


def _market_data(
    *,
    orderbook: list[dict[str, object]] | None = None,
    trades: list[dict[str, object]] | None = None,
    fundings: list[dict[str, object]] | None = None,
) -> MarketData:
    return MarketData(
        orderbook=pd.DataFrame(orderbook if orderbook is not None else [_book_row("2026-03-19T00:00:00Z")]),
        trades=pd.DataFrame(
            trades
            if trades is not None
            else [
                {
                    "datetime": pd.Timestamp("2026-03-19T00:00:01Z"),
                    "price": 99.0,
                    "size": 1.0,
                    "is_maker_ask": 0,
                    "_source_day": "2026-03-19",
                    "_row_id": 0,
                }
            ]
        ),
        fundings=pd.DataFrame(
            fundings
            if fundings is not None
            else [
                {
                    "datetime": pd.Timestamp("2026-03-19T00:00:00Z"),
                    "funding_rate": 0.0,
                    "_source_day": "2026-03-19",
                    "_row_id": 0,
                }
            ]
        ),
    )


def _audit_value(result: AuditResult, check: str) -> object:
    row = result.summary.loc[result.summary["check"] == check].iloc[0]
    return row["value"]


def test_tick_rounding_handles_decimal_ticks():
    assert floor_to_tick(100.3, 0.1) == pytest.approx(100.3)
    assert ceil_to_tick(100.1, 0.1) == pytest.approx(100.1)
    assert floor_to_tick(100.39, 0.1) == pytest.approx(100.3)
    assert ceil_to_tick(100.31, 0.1) == pytest.approx(100.4)


def test_spread_tick_comparison_uses_rounded_tick_count():
    cfg = _config().strategy
    risk_cfg = _config().risk
    strategy = MarketMakingStrategy(cfg, risk_cfg, tick_size=0.1)
    book = _book_state(100.0, 100.09999999999991)

    decision = strategy.quote(
        timestamp=pd.Timestamp("2026-03-19T00:00:00Z"),
        book=book,
        account=AccountingState(),
        features=Simulator(_market_data(), _config(), 0.1).features,
        latest_funding_rate=0.0,
        risk=Simulator(_market_data(), _config(), 0.1).risk,
        day_end=pd.Timestamp("2026-03-20T00:00:00Z"),
    )

    assert decision.reason == "ok"


def test_eod_reduce_only_does_not_open_or_flip_inventory():
    cfg = _config(eod_reduce_window_minutes=15)
    strategy = MarketMakingStrategy(cfg.strategy, cfg.risk, tick_size=1.0)
    timestamp = pd.Timestamp("2026-03-19T23:50:00Z")
    day_end = pd.Timestamp("2026-03-20T00:00:00Z")
    book = _book_state()
    features = Simulator(_market_data(), cfg, 1.0).features
    risk = Simulator(_market_data(), cfg, 1.0).risk

    flat = strategy.quote(timestamp, book, AccountingState(inventory=0.0), features, 0.0, risk, day_end)
    assert flat.bid_size == pytest.approx(0.0)
    assert flat.ask_size == pytest.approx(0.0)

    long = strategy.quote(timestamp, book, AccountingState(inventory=0.03), features, 0.0, risk, day_end)
    assert long.bid_size == pytest.approx(0.0)
    assert long.ask_size <= 0.03

    short = strategy.quote(timestamp, book, AccountingState(inventory=-0.02), features, 0.0, risk, day_end)
    assert short.ask_size == pytest.approx(0.0)
    assert short.bid_size <= 0.02


def test_simulator_eod_reduce_only_cancels_stale_flat_orders_before_trades():
    data = _market_data(
        orderbook=[_book_row("2026-03-19T23:44:50Z", 99.0, 101.0, row_id=0)],
        trades=[
            {
                "datetime": pd.Timestamp("2026-03-19T23:45:01Z"),
                "price": 99.0,
                "size": 1.0,
                "is_maker_ask": 0,
                "_source_day": "2026-03-19",
                "_row_id": 0,
            }
        ],
    )
    config = _config(refresh_interval_seconds=3600, eod_reduce_window_minutes=15)

    result = Simulator(data, config, tick_size=1.0).run()

    assert result.fills.empty
    cancels = result.orders[result.orders["event"] == "cancelled"]
    assert not cancels.empty
    assert set(cancels["reason"]) == {"eod_reduce_only_flat"}
    assert set(cancels["timestamp"]) == {pd.Timestamp("2026-03-19T23:45:01Z")}


def test_simulator_eod_reduce_only_caps_existing_reduce_side_order():
    simulator = Simulator(_market_data(), _config(eod_reduce_window_minutes=15), tick_size=1.0)
    timestamp = pd.Timestamp("2026-03-19T23:50:00Z")
    simulator.account.inventory = 0.03
    simulator.active_orders[Side.BID] = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=timestamp - pd.Timedelta(seconds=10),
        active_time=timestamp - pd.Timedelta(seconds=10),
    )
    simulator.active_orders[Side.ASK] = LiveOrder(
        order_id=2,
        side=Side.ASK,
        price=101.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=timestamp - pd.Timedelta(seconds=10),
        active_time=timestamp - pd.Timedelta(seconds=10),
    )

    simulator._enforce_reduce_only_orders(timestamp)

    assert simulator.active_orders[Side.BID] is None
    assert simulator.active_orders[Side.ASK].remaining_quantity == pytest.approx(0.03)
    assert simulator.order_rows[-1]["event"] == "resized"
    assert simulator.order_rows[-1]["reason"] == "eod_reduce_only_cap"


def test_daily_summary_reports_incremental_pnl_components():
    equity = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-03-19T23:59:00Z", "2026-03-20T23:59:00Z"], utc=True),
            "equity": [10.0, 15.0],
            "realized_trading_pnl": [7.0, 9.0],
            "unrealized_trading_pnl": [2.0, 3.0],
            "funding_pnl": [1.5, 4.0],
            "fees": [0.5, 0.8],
            "inventory": [0.1, 0.2],
        }
    )

    daily = daily_summary(equity, pd.DataFrame())

    assert daily["daily_pnl"].tolist() == pytest.approx([10.0, 5.0])
    assert daily["daily_realized_trading_pnl"].tolist() == pytest.approx([7.0, 2.0])
    assert daily["daily_unrealized_trading_pnl_change"].tolist() == pytest.approx([2.0, 1.0])
    assert daily["daily_funding_pnl"].tolist() == pytest.approx([1.5, 2.5])
    assert daily["daily_fees"].tolist() == pytest.approx([0.5, 0.3])


def test_report_uses_actual_fill_model_label():
    cfg = _config(fill_model="simple")
    metrics = MetricsBundle(
        overall=pd.DataFrame(),
        daily=pd.DataFrame(),
        fill_stats=pd.DataFrame(),
        order_stats=pd.DataFrame(),
        inventory_stats=pd.DataFrame(),
        realized_spread=pd.DataFrame(),
    )
    result = BacktestResult(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), metrics, 0.0)
    audit = AuditResult(
        tick_size=1.0,
        summary=pd.DataFrame([{"check": "tick_inference", "severity": "ok", "value": 1.0, "detail": "test"}]),
        spread_stats={"one_tick_or_less_pct": 0.0},
        depth_stats={"bid_depth_1_p50": 1.0},
    )

    report = build_markdown_report(result, audit, cfg)

    assert "- Fill model: `simple`." in report
    assert "Official result uses the conservative queue-ahead fill model" not in report


def test_volatility_history_updates_only_on_book_mid_updates():
    features = RollingFeatures(mid_window_seconds=60)
    features.update_mid(pd.Timestamp("2026-03-19T00:00:00Z"), 100.0)
    features.update_mid(pd.Timestamp("2026-03-19T00:00:01Z"), 101.0)
    features.update_mid(pd.Timestamp("2026-03-19T00:00:02Z"), 103.0)
    history_len = len(features.volatility_history)

    for _ in range(5):
        features.volatility_buffer(quote_horizon_seconds=5.0, k_vol=1.0)
        features.high_volatility()
        features.update_trade(pd.Timestamp("2026-03-19T00:00:03Z"), is_maker_ask=1, size=1.0)

    assert len(features.volatility_history) == history_len
    features.update_mid(pd.Timestamp("2026-03-19T00:00:03Z"), 104.0)
    assert len(features.volatility_history) == history_len + 1


def test_cancel_all_uses_current_event_timestamp_not_stale_book_timestamp():
    simulator = Simulator(_market_data(), _config(), tick_size=1.0)
    stale_book_time = pd.Timestamp("2026-03-19T00:00:00Z")
    cancel_time = pd.Timestamp("2026-03-19T00:00:03Z")
    simulator.book.update_from_row(pd.Series(_book_row(str(stale_book_time))))
    simulator.active_orders[Side.ASK] = LiveOrder(
        order_id=1,
        side=Side.ASK,
        price=101.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=stale_book_time,
        active_time=stale_book_time,
    )

    simulator._cancel_all("refresh", cancel_time)

    assert simulator.order_rows[-1]["timestamp"] == cancel_time


def test_audit_duplicate_rows_ignore_loader_metadata():
    row0 = _book_row("2026-03-19T00:00:00Z", row_id=0)
    row1 = dict(row0)
    row1["_row_id"] = 1

    result = run_audit(_market_data(orderbook=[row0, row1]), _config().audit)

    assert _audit_value(result, "orderbook_duplicate_rows") == 1


def test_audit_rejects_bad_trade_side_and_size():
    result = run_audit(
        _market_data(
            trades=[
                {
                    "datetime": pd.Timestamp("2026-03-19T00:00:01Z"),
                    "price": 99.0,
                    "size": 0.0,
                    "is_maker_ask": 2,
                    "_source_day": "2026-03-19",
                    "_row_id": 0,
                }
            ]
        ),
        _config().audit,
    )

    assert _audit_value(result, "trade_side_values") == 1
    assert _audit_value(result, "trade_positive_size") == 1
    bad_rows = result.summary[result.summary["check"].isin(["trade_side_values", "trade_positive_size"])]
    assert set(bad_rows["severity"]) == {"error"}


def test_liquidation_adjusted_equity_marks_long_to_bid_and_short_to_ask():
    long_account = AccountingState(cash=-100.0, inventory=1.0)
    short_account = AccountingState(cash=100.0, inventory=-1.0)

    assert long_account.liquidation_adjusted_equity(99.0, 101.0) == pytest.approx(-1.0)
    assert short_account.liquidation_adjusted_equity(99.0, 101.0) == pytest.approx(-1.0)


def test_event_level_drawdown_captures_intraminute_loss():
    data = _market_data(
        orderbook=[
            _book_row("2026-03-19T00:00:00Z", 99.0, 101.0, row_id=0),
            _book_row("2026-03-19T00:00:02Z", 60.0, 62.0, row_id=1),
            _book_row("2026-03-19T00:00:03Z", 100.0, 102.0, row_id=2),
        ],
        trades=[
            {
                "datetime": pd.Timestamp("2026-03-19T00:00:01Z"),
                "price": 99.0,
                "size": 1.0,
                "is_maker_ask": 0,
                "_source_day": "2026-03-19",
                "_row_id": 0,
            }
        ],
    )

    result = Simulator(data, _config(report_frequency="1min"), tick_size=1.0).run()
    summary = result.metrics.overall.iloc[0]

    assert summary["max_drawdown"] >= 38.0
    assert summary["max_drawdown"] > summary["sampled_1m_max_drawdown"]


def test_queue_ahead_includes_better_and_equal_price_depth():
    book = BookState()
    assert book.update(
        timestamp=pd.Timestamp("2026-03-19T00:00:00Z"),
        bids=[(100.0, 3.0), (99.0, 4.0), (98.0, 5.0)],
        asks=[(101.0, 2.0), (102.0, 6.0), (103.0, 7.0)],
    )

    assert book.queue_ahead(Side.BID, 99.0) == pytest.approx(7.0)
    assert book.queue_ahead(Side.ASK, 102.0) == pytest.approx(8.0)
