from __future__ import annotations

import pandas as pd

from market_maker.config import AuditConfig
from market_maker.data_audit import run_audit, run_audit_by_day
from market_maker.data_loader import MarketData


def audit_config() -> AuditConfig:
    return AuditConfig(
        max_funding_staleness_seconds=120,
        trade_alignment_tolerance_ticks=2,
        tick_sample_size=100,
        mid_jump_warn_ticks=20.0,
        stale_book_warn_ms=1000.0,
        one_tick_spread_warn_pct=50.0,
        funding_abs_warn_threshold=0.01,
    )


def orderbook_row(timestamp: str, row_id: int = 0, source_day: str = "2026-03-19") -> dict[str, object]:
    row: dict[str, object] = {
        "datetime": pd.Timestamp(timestamp),
        "_source_day": source_day,
        "_row_id": row_id,
    }
    for level in range(1, 21):
        row[f"bid_price_{level}"] = 100.0 - (level - 1) * 0.1
        row[f"ask_price_{level}"] = 100.1 + (level - 1) * 0.1
        row[f"bid_qty_{level}"] = 1.0
        row[f"ask_qty_{level}"] = 1.0
    return row


def market_data(orderbook: pd.DataFrame, trades: pd.DataFrame | None = None, fundings: pd.DataFrame | None = None) -> MarketData:
    if trades is None:
        trades = pd.DataFrame(
            [
                {
                    "datetime": pd.Timestamp("2026-03-19T00:00:00Z"),
                    "price": 100.1,
                    "size": 1.0,
                    "is_maker_ask": 1,
                    "_source_day": "2026-03-19",
                    "_row_id": 0,
                }
            ]
        )
    if fundings is None:
        fundings = pd.DataFrame(
            [
                {
                    "datetime": pd.Timestamp("2026-03-19T00:00:00Z"),
                    "funding_rate": 0.0,
                    "_source_day": "2026-03-19",
                    "_row_id": 0,
                }
            ]
        )
    return MarketData(orderbook=orderbook, trades=trades, fundings=fundings)


def check_value(summary: pd.DataFrame, check: str) -> object:
    return summary.loc[summary["check"] == check, "value"].iloc[0]


def check_severity(summary: pd.DataFrame, check: str) -> str:
    return str(summary.loc[summary["check"] == check, "severity"].iloc[0])


def test_duplicate_rows_ignore_loader_metadata():
    first = orderbook_row("2026-03-19T00:00:00Z", row_id=0, source_day="2026-03-19")
    duplicate_market_row = orderbook_row("2026-03-19T00:00:00Z", row_id=99, source_day="2026-03-20")
    result = run_audit(market_data(pd.DataFrame([first, duplicate_market_row])), audit_config())

    assert check_value(result.summary, "orderbook_duplicate_rows") == 1
    assert check_severity(result.summary, "orderbook_duplicate_rows") == "warn"


def test_trade_side_and_size_validation_are_errors():
    orderbook = pd.DataFrame([orderbook_row("2026-03-19T00:00:00Z")])
    trades = pd.DataFrame(
        [
            {
                "datetime": pd.Timestamp("2026-03-19T00:00:00Z"),
                "price": 100.1,
                "size": 0.0,
                "is_maker_ask": 2,
                "_source_day": "2026-03-19",
                "_row_id": 0,
            }
        ]
    )

    result = run_audit(market_data(orderbook, trades=trades), audit_config())

    assert check_severity(result.summary, "trade_side_values") == "error"
    assert check_severity(result.summary, "trade_positive_size") == "error"
    assert not result.passed


def test_alignment_age_and_visible_l2_checks_are_reported():
    orderbook = pd.DataFrame([orderbook_row("2026-03-19T00:00:00Z")])
    trades = pd.DataFrame(
        [
            {
                "datetime": pd.Timestamp("2026-03-19T00:00:02Z"),
                "price": 105.0,
                "size": 1.0,
                "is_maker_ask": 1,
                "_source_day": "2026-03-19",
                "_row_id": 0,
            }
        ]
    )

    result = run_audit(market_data(orderbook, trades=trades), audit_config())

    assert check_value(result.summary, "trade_price_outside_visible_l2") == 1
    assert check_severity(result.summary, "trade_book_alignment_age_ms") == "warn"


def test_run_audit_by_day_preserves_full_scope_with_day_labels(tmp_path):
    data_dir = tmp_path / "data"
    for folder in ["orderbook", "trades", "fundings"]:
        (data_dir / folder).mkdir(parents=True)
    for day in ["2026-03-19", "2026-03-20"]:
        orderbook = pd.DataFrame([orderbook_row(f"{day}T00:00:00Z", source_day=day)])
        trades = pd.DataFrame(
            [
                {
                    "datetime": pd.Timestamp(f"{day}T00:00:00Z"),
                    "price": 100.1,
                    "size": 1.0,
                    "is_maker_ask": 1,
                }
            ]
        )
        fundings = pd.DataFrame([{"datetime": pd.Timestamp(f"{day}T00:00:00Z"), "funding_rate": 0.0}])
        orderbook.to_parquet(data_dir / "orderbook" / f"{day}.parquet", index=False)
        trades.to_parquet(data_dir / "trades" / f"{day}.parquet", index=False)
        fundings.to_parquet(data_dir / "fundings" / f"{day}.parquet", index=False)

    result = run_audit_by_day(data_dir, ["2026-03-19", "2026-03-20"], audit_config())

    assert result.passed
    assert set(result.summary["day"]) == {"2026-03-19", "2026-03-20"}
    assert result.event_ordering_stats["days_audited"] == 2
    assert result.event_ordering_stats["book_rows"] == 2
    assert result.spread_stats["days_audited"] == 2.0
