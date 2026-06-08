from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from market_maker import cli
from market_maker.config import AuditConfig, BacktestConfig, DataConfig, ExecutionConfig, RiskConfig, StrategyConfig
from market_maker.data_audit import AuditResult
from market_maker.data_loader import MarketData
from market_maker.orders import LiveOrder, Side
from market_maker.simulator import Simulator


def config(
    *,
    fill_model: str = "simple",
    cancel_latency_ms: int = 0,
    queue_depletion_fraction: float = 0.0,
    pressure_stop: float = 1.0,
    w_book: float = 0.0,
    stale_book_max_age_ms: float = 1000.0,
) -> BacktestConfig:
    return BacktestConfig(
        data=DataConfig(data_dir="data", days=("2026-03-19",)),
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=0,
            cancel_latency_ms=cancel_latency_ms,
            fill_model=fill_model,
            queue_depletion_fraction=queue_depletion_fraction,
            funding_period_hours=8.0,
            report_frequency="1min",
            stale_book_max_age_ms=stale_book_max_age_ms,
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
            pressure_stop=pressure_stop,
            w_book=w_book,
            w_trade=0.0,
            refresh_interval_seconds=60,
            max_quote_age_seconds=600,
            requote_bbo_ticks=100,
            requote_delta_ticks=100,
            funding_retarget_threshold=1.0,
        ),
        risk=RiskConfig(
            max_drawdown_usd=1_000.0,
            vol_widen_multiplier=2.0,
            jump_ticks_stop=100,
            cooldown_seconds=10,
            eod_reduce_window_minutes=0,
            min_economic_spread_ticks=1,
        ),
        audit=AuditConfig(
            max_funding_staleness_seconds=120,
            trade_alignment_tolerance_ticks=2,
            tick_sample_size=100,
        ),
    )


def book_row(
    timestamp: str,
    *,
    bid: float = 99.0,
    ask: float = 101.0,
    bid_qty_1: float = 10.0,
    ask_qty_1: float = 10.0,
) -> dict[str, object]:
    row: dict[str, object] = {"datetime": pd.Timestamp(timestamp)}
    for level in range(1, 21):
        row[f"bid_price_{level}"] = bid - (level - 1)
        row[f"ask_price_{level}"] = ask + (level - 1)
        row[f"bid_qty_{level}"] = bid_qty_1 if level == 1 else 10.0
        row[f"ask_qty_{level}"] = ask_qty_1 if level == 1 else 10.0
    return row


def market_data(orderbook: list[dict[str, object]], trades: list[dict[str, object]] | None = None) -> MarketData:
    trades_df = pd.DataFrame(
        trades if trades is not None else [],
        columns=["datetime", "price", "size", "is_maker_ask"],
    )
    return MarketData(
        orderbook=pd.DataFrame(orderbook),
        trades=trades_df,
        fundings=pd.DataFrame([{"datetime": pd.Timestamp("2026-03-19T00:00:00Z"), "funding_rate": 0.0}]),
    )


def test_pressure_stop_cancels_existing_bid_before_later_trade():
    data = market_data(
        [
            book_row("2026-03-19T00:00:00Z"),
            book_row("2026-03-19T00:00:01Z", bid_qty_1=1.0, ask_qty_1=100.0),
        ],
        [
            {
                "datetime": pd.Timestamp("2026-03-19T00:00:02Z"),
                "price": 99.0,
                "size": 1.0,
                "is_maker_ask": 0,
            }
        ],
    )

    result = Simulator(data, config(pressure_stop=0.5, w_book=1.0), tick_size=1.0).run()

    assert result.fills.empty
    cancels = result.orders[result.orders["event"] == "cancelled"]
    assert "pressure_stop_bid" in set(cancels["reason"])


def test_pending_cancel_order_can_fill_before_cancel_effective_time():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    simulator = Simulator(market_data([book_row(str(timestamp))]), config(cancel_latency_ms=500), tick_size=1.0)
    assert simulator.book.update_from_row(pd.Series(book_row(str(timestamp))))
    simulator.active_orders[Side.BID] = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=timestamp,
        active_time=timestamp,
        queue_ahead=0.0,
    )

    simulator._cancel_order(Side.BID, "pressure_stop_bid", timestamp)
    simulator._process_trade_values(timestamp + pd.Timedelta(milliseconds=100), 99.0, 1.0, 0)

    assert simulator.fill_rows
    assert simulator.fill_rows[0]["is_pending_cancel_fill"] is True
    assert simulator.active_orders[Side.BID] is None


def test_partial_queue_depletes_from_visible_book_reduction():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    simulator = Simulator(
        market_data([book_row(str(timestamp))]),
        config(fill_model="partial_queue", queue_depletion_fraction=0.5),
        tick_size=1.0,
    )
    assert simulator.book.update_from_row(pd.Series(book_row(str(timestamp))))
    order = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=timestamp,
        active_time=timestamp,
        queue_ahead=10.0,
        last_visible_queue_ahead=10.0,
    )
    simulator.active_orders[Side.BID] = order

    row = book_row("2026-03-19T00:00:01Z", bid_qty_1=6.0)
    simulator._process_orderbook_values(
        pd.Timestamp(row["datetime"]),
        pd.Series([row[f"bid_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row[f"bid_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row[f"ask_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row[f"ask_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
    )

    assert order.queue_ahead == pytest.approx(8.0)


def test_fill_rows_include_markouts_and_required_diagnostics():
    data = market_data(
        [
            book_row("2026-03-19T00:00:00Z"),
            book_row("2026-03-19T00:00:01Z", bid=98.0, ask=100.0),
            book_row("2026-03-19T00:00:05Z", bid=97.0, ask=99.0),
        ],
        [
            {
                "datetime": pd.Timestamp("2026-03-19T00:00:00.500Z"),
                "price": 99.0,
                "size": 1.0,
                "is_maker_ask": 0,
            }
        ],
    )

    fills = Simulator(data, config(), tick_size=1.0).run().fills

    required = {
        "pressure_at_placement",
        "pressure_at_fill",
        "trade_imbalance_at_fill",
        "quote_age_ms",
        "book_age_ms",
        "queue_ahead_initial",
        "queue_ahead_before_fill",
        "fill_model",
        "markout_1s",
        "realized_spread_5s",
    }
    assert not fills.empty
    assert required.issubset(fills.columns)


def test_forced_flat_pnl_includes_slippage_cost():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    cfg = config()
    cfg = BacktestConfig(
        data=cfg.data,
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=0,
            cancel_latency_ms=0,
            fill_model="simple",
            funding_period_hours=8.0,
            report_frequency="1min",
            force_flat_slippage_bps=10.0,
        ),
        strategy=cfg.strategy,
        risk=cfg.risk,
        audit=cfg.audit,
    )
    simulator = Simulator(market_data([book_row(str(timestamp))]), cfg, tick_size=1.0)
    assert simulator.book.update_from_row(pd.Series(book_row(str(timestamp))))
    simulator.account.cash = -99.0
    simulator.account.inventory = 1.0

    assert simulator._forced_flat_equity() < simulator._liquidation_equity()


def test_forced_flat_pnl_charges_configured_closing_fee():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    cfg = config()
    cfg = BacktestConfig(
        data=cfg.data,
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=0,
            cancel_latency_ms=0,
            fill_model="simple",
            funding_period_hours=8.0,
            report_frequency="1min",
            force_flat_slippage_bps=0.0,
            force_flat_fee_bps=10.0,
        ),
        strategy=cfg.strategy,
        risk=cfg.risk,
        audit=cfg.audit,
    )
    simulator = Simulator(market_data([book_row(str(timestamp))]), cfg, tick_size=1.0)
    assert simulator.book.update_from_row(pd.Series(book_row(str(timestamp))))
    simulator.account.cash = -99.0
    simulator.account.inventory = 1.0

    assert simulator._forced_flat_equity() == pytest.approx(-0.099)


def test_forced_flat_pnl_charges_fee_with_previous_mark_fallback():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    cfg = config()
    cfg = BacktestConfig(
        data=cfg.data,
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=0,
            cancel_latency_ms=0,
            fill_model="simple",
            funding_period_hours=8.0,
            report_frequency="1min",
            force_flat_slippage_bps=0.0,
            force_flat_fee_bps=10.0,
        ),
        strategy=cfg.strategy,
        risk=cfg.risk,
        audit=cfg.audit,
    )
    simulator = Simulator(market_data([book_row(str(timestamp))]), cfg, tick_size=1.0)
    simulator.previous_mark = 100.0
    simulator.account.cash = -99.0
    simulator.account.inventory = 1.0

    assert simulator._forced_flat_equity() == pytest.approx(0.9)


def test_robustness_command_writes_grid_and_pivot(monkeypatch, tmp_path):
    cfg = config(fill_model="partial_queue", queue_depletion_fraction=0.5)
    data = market_data([book_row("2026-03-19T00:00:00Z")], [])
    audit = AuditResult(
        tick_size=1.0,
        summary=pd.DataFrame([{"check": "ok", "severity": "ok", "value": 0, "detail": "ok"}]),
        warnings=[],
        spread_stats={},
        depth_stats={},
    )

    monkeypatch.setattr(cli, "load_config", lambda _: cfg)
    monkeypatch.setattr(cli, "load_market_data", lambda *_: data)
    monkeypatch.setattr(cli, "load_market_data_sample", lambda *_args, **_kwargs: data)
    monkeypatch.setattr(cli, "run_audit", lambda *_: audit)

    cli.run_command(
        SimpleNamespace(
            command="robustness",
            config="config/default.yaml",
            data_dir=None,
            output_dir=str(tmp_path),
            fill_model=None,
            maker_fee_bps=None,
            cancel_latency_ms=None,
            queue_depletion_fraction=None,
            funding_target_frac=None,
            pressure_stop=None,
            min_half_spread_ticks=None,
            suite_size="smoke",
            allow_audit_errors=False,
        )
    )

    assert (tmp_path / "grid_results.csv").exists()
    assert (tmp_path / "pnl_by_queue_depletion_cancel_latency.csv").exists()


def test_full_core_robustness_variants_match_review_contract():
    variants = [name for name, _ in cli._full_core_robustness_variants(config())]

    assert variants == [
        "baseline",
        "simple_fill",
        "partial_queue_0.25",
        "partial_queue_0.50",
        "cancel_latency_0",
        "cancel_latency_500",
        "pressure_filter_off",
        "fee_0bps",
        "fee_1bps",
    ]


def test_partial_queue_depletion_starts_after_order_active_time():
    timestamp = pd.Timestamp("2026-03-19T00:00:00Z")
    simulator = Simulator(
        market_data([book_row(str(timestamp))]),
        config(fill_model="partial_queue", queue_depletion_fraction=0.5),
        tick_size=1.0,
    )
    assert simulator.book.update_from_row(pd.Series(book_row(str(timestamp))))
    order = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=timestamp,
        active_time=timestamp + pd.Timedelta(seconds=1),
        queue_ahead=10.0,
        last_visible_queue_ahead=10.0,
    )
    simulator.active_orders[Side.BID] = order

    row_before_active = book_row("2026-03-19T00:00:00.500Z", bid_qty_1=6.0)
    simulator._process_orderbook_values(
        pd.Timestamp(row_before_active["datetime"]),
        pd.Series([row_before_active[f"bid_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_before_active[f"bid_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_before_active[f"ask_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_before_active[f"ask_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
    )
    assert order.queue_ahead == pytest.approx(10.0)
    assert order.last_visible_queue_ahead == pytest.approx(6.0)

    row_after_active = book_row("2026-03-19T00:00:02Z", bid_qty_1=4.0)
    simulator._process_orderbook_values(
        pd.Timestamp(row_after_active["datetime"]),
        pd.Series([row_after_active[f"bid_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_after_active[f"bid_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_after_active[f"ask_price_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
        pd.Series([row_after_active[f"ask_qty_{level}"] for level in range(1, 21)]).to_numpy(dtype=float),
    )

    assert order.queue_ahead == pytest.approx(9.0)
