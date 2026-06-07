from dataclasses import replace

import pandas as pd

from market_maker.config import AuditConfig, BacktestConfig, DataConfig, ExecutionConfig, RiskConfig, StrategyConfig
from market_maker.data_loader import MarketData, load_market_data
from market_maker.orders import LiveOrder, Side
from market_maker.simulator import Simulator


def config(latency_ms: int = 250) -> BacktestConfig:
    return BacktestConfig(
        data=DataConfig(data_dir="data", days=("2026-03-19",)),
        execution=ExecutionConfig(
            maker_fee_bps=0.0,
            latency_ms=latency_ms,
            fill_model="simple",
            funding_period_hours=8.0,
            report_frequency="1min",
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
            refresh_interval_seconds=60,
            max_quote_age_seconds=60,
            requote_bbo_ticks=100,
            requote_delta_ticks=100,
            funding_retarget_threshold=1.0,
        ),
        risk=RiskConfig(
            max_drawdown_usd=100.0,
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


def book_row(timestamp: str) -> dict[str, object]:
    row: dict[str, object] = {"datetime": pd.Timestamp(timestamp)}
    for level in range(1, 21):
        row[f"bid_price_{level}"] = 99.0 - (level - 1)
        row[f"ask_price_{level}"] = 101.0 + (level - 1)
        row[f"bid_qty_{level}"] = 10.0
        row[f"ask_qty_{level}"] = 10.0
    return row


def test_loader_preserves_file_order_for_same_timestamp_trades(tmp_path):
    day = "2026-03-19"
    data_dir = tmp_path / "data"
    (data_dir / "orderbook").mkdir(parents=True)
    (data_dir / "trades").mkdir()
    (data_dir / "fundings").mkdir()
    pd.DataFrame([book_row(f"{day}T00:00:00Z")]).to_parquet(data_dir / "orderbook" / f"{day}.parquet")
    pd.DataFrame(
        [
            {"datetime": pd.Timestamp(f"{day}T00:00:01Z"), "price": 101.0, "size": 1.0, "is_maker_ask": 1},
            {"datetime": pd.Timestamp(f"{day}T00:00:00Z"), "price": 99.0, "size": 2.0, "is_maker_ask": 0},
            {"datetime": pd.Timestamp(f"{day}T00:00:00Z"), "price": 98.5, "size": 3.0, "is_maker_ask": 0},
        ]
    ).to_parquet(data_dir / "trades" / f"{day}.parquet")
    pd.DataFrame([{"datetime": pd.Timestamp(f"{day}T00:00:00Z"), "funding_rate": 0.0}]).to_parquet(data_dir / "fundings" / f"{day}.parquet")

    loaded = load_market_data(data_dir, [day])
    same_time = loaded.trades[loaded.trades["datetime"] == pd.Timestamp(f"{day}T00:00:00Z", tz="UTC")]

    assert same_time["_row_id"].tolist() == [1, 2]
    assert same_time["size"].tolist() == [2.0, 3.0]


def test_same_timestamp_trade_cannot_fill_new_quote():
    t0 = "2026-03-19T00:00:00Z"
    data = MarketData(
        orderbook=pd.DataFrame([book_row(t0)]),
        trades=pd.DataFrame(
            [
                {
                    "datetime": pd.Timestamp(t0),
                    "price": 99.0,
                    "size": 1.0,
                    "is_maker_ask": 0,
                }
            ]
        ),
        fundings=pd.DataFrame([{"datetime": pd.Timestamp(t0), "funding_rate": 0.0}]),
    )
    result = Simulator(data, config(latency_ms=0), tick_size=1.0).run()
    assert result.fills.empty


def test_cancel_records_event_timestamp_not_stale_book_timestamp():
    book_time = pd.Timestamp("2026-03-19T00:00:00Z")
    cancel_time = pd.Timestamp("2026-03-19T00:00:01Z")
    data = MarketData(
        orderbook=pd.DataFrame([book_row(str(book_time))]),
        trades=pd.DataFrame(columns=["datetime", "price", "size", "is_maker_ask"]),
        fundings=pd.DataFrame([{"datetime": book_time, "funding_rate": 0.0}]),
    )
    simulator = Simulator(data, config(latency_ms=0), tick_size=1.0)
    assert simulator.book.update_from_row(pd.Series(book_row(str(book_time))))
    simulator.active_orders[Side.BID] = LiveOrder(
        order_id=1,
        side=Side.BID,
        price=99.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        created_time=book_time,
        active_time=book_time,
        queue_ahead=10.0,
    )

    simulator._cancel_all("refresh", cancel_time)

    assert simulator.order_rows[0]["timestamp"] == cancel_time


def test_trade_triggered_refresh_cancels_at_trade_timestamp_not_stale_book_timestamp():
    t0 = "2026-03-19T00:00:00Z"
    t1 = "2026-03-19T00:00:01Z"
    data = MarketData(
        orderbook=pd.DataFrame([book_row(t0)]),
        trades=pd.DataFrame(
            [
                {
                    "datetime": pd.Timestamp(t1),
                    "price": 99.0,
                    "size": 1.0,
                    "is_maker_ask": 0,
                }
            ]
        ),
        fundings=pd.DataFrame([{"datetime": pd.Timestamp(t0), "funding_rate": 0.0}]),
    )
    cfg = config(latency_ms=0)
    cfg = replace(cfg, strategy=replace(cfg.strategy, theta_inv=1.0, requote_delta_ticks=0))

    result = Simulator(data, cfg, tick_size=1.0).run()
    cancelled = result.orders[result.orders["event"] == "cancelled"]

    assert not cancelled.empty
    assert pd.Timestamp(t1) in set(cancelled["timestamp"])
    assert pd.Timestamp(t0) not in set(cancelled["timestamp"])
