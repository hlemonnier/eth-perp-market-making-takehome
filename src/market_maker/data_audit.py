from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from market_maker.book_state import LEVELS
from market_maker.config import AuditConfig
from market_maker.data_loader import FUNDING_COLUMNS, ORDERBOOK_COLUMNS, TRADE_COLUMNS, MarketData


@dataclass
class AuditResult:
    tick_size: float
    summary: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    spread_stats: dict[str, float] = field(default_factory=dict)
    depth_stats: dict[str, float] = field(default_factory=dict)
    event_ordering_stats: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(row["severity"] == "error" for _, row in self.summary.iterrows())


def _add(rows: list[dict[str, object]], check: str, severity: str, value: object, detail: str) -> None:
    rows.append({"check": check, "severity": severity, "value": value, "detail": detail})


def _duplicate_subset(label: str, df: pd.DataFrame) -> list[str]:
    if label == "orderbook":
        top_levels = [1, 2, 3]
        subset = ["datetime"]
        subset.extend(
            column
            for level in top_levels
            for column in (f"bid_price_{level}", f"bid_qty_{level}", f"ask_price_{level}", f"ask_qty_{level}")
            if column in df.columns
        )
        return subset
    if label == "trades":
        return [column for column in ["datetime", "price", "size", "is_maker_ask"] if column in df.columns]
    if label == "fundings":
        return [column for column in ["datetime", "funding_rate"] if column in df.columns]
    metadata_cols = {"_source_day", "_row_id"}
    return [column for column in df.columns if column not in metadata_cols]


def infer_tick_size(data: MarketData, sample_size: int = 250_000) -> float:
    samples = [
        data.orderbook["bid_price_1"].head(sample_size),
        data.orderbook["ask_price_1"].head(sample_size),
        data.trades["price"].head(sample_size),
    ]
    prices = pd.concat(samples, ignore_index=True).dropna().astype(float)
    if prices.empty:
        raise ValueError("Cannot infer tick size without prices")
    unique_prices = np.sort(np.unique(np.round(prices.to_numpy(), 8)))
    diffs = np.diff(unique_prices)
    diffs = diffs[(diffs > 1e-8) & np.isfinite(diffs)]
    if len(diffs) == 0:
        return 0.01
    rounded = np.round(diffs, 8)
    values, counts = np.unique(rounded, return_counts=True)
    return float(values[np.argmax(counts)])


def run_audit(data: MarketData, config: AuditConfig) -> AuditResult:
    rows: list[dict[str, object]] = []
    warnings: list[str] = []

    schema_checks = [
        ("orderbook_schema", data.orderbook, ORDERBOOK_COLUMNS),
        ("trades_schema", data.trades, TRADE_COLUMNS),
        ("fundings_schema", data.fundings, FUNDING_COLUMNS),
    ]
    for name, df, required in schema_checks:
        missing = [column for column in required if column not in df.columns]
        severity = "error" if missing else "ok"
        _add(rows, name, severity, len(missing), f"missing={missing}")

    for name, df in [("orderbook", data.orderbook), ("trades", data.trades), ("fundings", data.fundings)]:
        disorder = int((df["datetime"].diff().dropna() < pd.Timedelta(0)).sum())
        _add(rows, f"{name}_timestamp_order", "error" if disorder else "ok", disorder, "negative timestamp diffs")
        nulls = int(df.drop(columns=[c for c in ["_source_day", "_row_id"] if c in df.columns]).isna().sum().sum())
        _add(rows, f"{name}_missing_values", "warn" if nulls else "ok", nulls, "null cells")
        dup_rows = int(df.duplicated(subset=_duplicate_subset(name, df)).sum())
        _add(rows, f"{name}_duplicate_rows", "warn" if dup_rows else "ok", dup_rows, "targeted duplicate rows excluding loader metadata")
        dup_times = int(df["datetime"].duplicated().sum())
        dup_time_pct = float(dup_times / len(df) * 100.0) if len(df) else 0.0
        _add(rows, f"{name}_duplicate_timestamps", "warn" if dup_times else "ok", dup_times, f"duplicate timestamps; pct={dup_time_pct:.4f}")

    bid_prices = data.orderbook[[f"bid_price_{i}" for i in LEVELS]].astype(float)
    ask_prices = data.orderbook[[f"ask_price_{i}" for i in LEVELS]].astype(float)
    bid_qty = data.orderbook[[f"bid_qty_{i}" for i in LEVELS]].astype(float)
    ask_qty = data.orderbook[[f"ask_qty_{i}" for i in LEVELS]].astype(float)
    bad_bid_monotone = int((bid_prices.diff(axis=1).iloc[:, 1:] > 0).any(axis=1).sum())
    bad_ask_monotone = int((ask_prices.diff(axis=1).iloc[:, 1:] < 0).any(axis=1).sum())
    bad_qty = int(((bid_qty < 0).any(axis=1) | (ask_qty < 0).any(axis=1)).sum())
    spread = data.orderbook["ask_price_1"].astype(float) - data.orderbook["bid_price_1"].astype(float)
    locked_or_crossed = int((spread <= 0).sum())
    _add(rows, "orderbook_bid_monotonicity", "error" if bad_bid_monotone else "ok", bad_bid_monotone, "rows with increasing bid levels")
    _add(rows, "orderbook_ask_monotonicity", "error" if bad_ask_monotone else "ok", bad_ask_monotone, "rows with decreasing ask levels")
    _add(rows, "orderbook_negative_quantities", "error" if bad_qty else "ok", bad_qty, "rows with negative qty")
    _add(rows, "orderbook_locked_or_crossed", "warn" if locked_or_crossed else "ok", locked_or_crossed, "rows with bid >= ask")

    tick_size = infer_tick_size(data, config.tick_sample_size)
    spread_ticks = spread / tick_size if tick_size > 0 else spread
    spread_stats = {
        "tick_size": tick_size,
        "spread_min": float(spread.min()),
        "spread_p05": float(spread.quantile(0.05)),
        "spread_p50": float(spread.quantile(0.50)),
        "spread_p95": float(spread.quantile(0.95)),
        "spread_p99": float(spread.quantile(0.99)),
        "spread_max": float(spread.max()),
        "spread_ticks_p50": float(spread_ticks.quantile(0.50)),
        "one_tick_or_less_pct": float((spread_ticks <= 1.0).mean() * 100.0),
    }
    _add(rows, "tick_inference", "ok", tick_size, "modal positive price increment")
    _add(rows, "spread_distribution", "ok", spread_stats["spread_p50"], f"stats={spread_stats}")
    one_tick_severity = "warn" if spread_stats["one_tick_or_less_pct"] >= config.one_tick_spread_warn_pct else "ok"
    _add(
        rows,
        "one_tick_spread_share",
        one_tick_severity,
        spread_stats["one_tick_or_less_pct"],
        "share of books with spread <= one inferred tick; high values leave little edge after fees/queue",
    )

    mid = (data.orderbook["bid_price_1"].astype(float) + data.orderbook["ask_price_1"].astype(float)) / 2.0
    mid_jump_ticks = mid.diff().abs() / tick_size if tick_size > 0 else mid.diff().abs()
    finite_mid_jumps = mid_jump_ticks[np.isfinite(mid_jump_ticks)]
    mid_jump_p99 = float(finite_mid_jumps.quantile(0.99)) if not finite_mid_jumps.empty else 0.0
    mid_jump_max = float(finite_mid_jumps.max()) if not finite_mid_jumps.empty else 0.0
    _add(
        rows,
        "mid_jump_outliers",
        "warn" if mid_jump_max > config.mid_jump_warn_ticks or mid_jump_p99 > config.mid_jump_warn_ticks else "ok",
        mid_jump_max,
        f"mid jump ticks p99={mid_jump_p99:.4f}, max={mid_jump_max:.4f}",
    )

    depth_stats: dict[str, float] = {}
    for levels in [1, 5, 10, 20]:
        bid_depth = bid_qty.iloc[:, :levels].sum(axis=1)
        ask_depth = ask_qty.iloc[:, :levels].sum(axis=1)
        depth_stats[f"bid_depth_{levels}_p50"] = float(bid_depth.quantile(0.5))
        depth_stats[f"ask_depth_{levels}_p50"] = float(ask_depth.quantile(0.5))
    _add(rows, "depth_distribution", "ok", depth_stats["bid_depth_1_p50"], f"stats={depth_stats}")

    if not data.trades.empty:
        finite_trade_values = np.isfinite(data.trades[["price", "size"]].astype(float)).all(axis=1)
        nonfinite_trade_values = int((~finite_trade_values).sum())
        _add(rows, "trade_price_size_finite", "error" if nonfinite_trade_values else "ok", nonfinite_trade_values, "non-finite trade price or size")
        bad_trade_side = int((~data.trades["is_maker_ask"].isin([0, 1])).sum())
        _add(rows, "trade_side_values", "error" if bad_trade_side else "ok", bad_trade_side, "is_maker_ask values outside {0,1}")
        nonpositive_trade_size = int((data.trades["size"].astype(float) <= 0).sum())
        _add(rows, "trade_positive_size", "error" if nonpositive_trade_size else "ok", nonpositive_trade_size, "trade rows with size <= 0")

    if not data.trades.empty and not data.orderbook.empty:
        event_ordering_stats = _event_ordering_sensitivity(data)
        same_ts_pct = float(event_ordering_stats["trades_with_same_timestamp_book_pct"])
        _add(
            rows,
            "trade_book_same_timestamp_share",
            "warn" if same_ts_pct > 0.0 else "ok",
            same_ts_pct,
            "trades sharing exact timestamps with book updates; default simulator policy processes equal-time trades before books",
        )
        orderbook_alignment_cols = ["datetime", "bid_price_1", "ask_price_1", "bid_price_20", "ask_price_20"]
        book_for_alignment = data.orderbook[orderbook_alignment_cols].sort_values("datetime").rename(columns={"datetime": "book_datetime"})
        aligned = pd.merge_asof(
            data.trades[["datetime", "price", "is_maker_ask"]].sort_values("datetime"),
            book_for_alignment,
            left_on="datetime",
            right_on="book_datetime",
            direction="backward",
        )
        tolerance = config.trade_alignment_tolerance_ticks * tick_size
        buy_bad = (aligned["is_maker_ask"] == 1) & (aligned["price"] < aligned["ask_price_1"] - tolerance)
        sell_bad = (aligned["is_maker_ask"] == 0) & (aligned["price"] > aligned["bid_price_1"] + tolerance)
        bad_alignment = int((buy_bad | sell_bad).fillna(False).sum())
        severity = "warn" if bad_alignment else "ok"
        _add(rows, "trade_book_alignment", severity, bad_alignment, "trades not near matching side of BBO")
        outside_l2 = int(((aligned["price"] < aligned["bid_price_20"] - tolerance) | (aligned["price"] > aligned["ask_price_20"] + tolerance)).fillna(False).sum())
        _add(rows, "trade_price_outside_visible_l2", "warn" if outside_l2 else "ok", outside_l2, "trades outside visible L2 price range after backward book alignment")
        age_ms = (aligned["datetime"] - aligned["book_datetime"]).dt.total_seconds() * 1000.0
        finite_age_ms = age_ms[np.isfinite(age_ms)]
        stale_stats = {
            "p50_ms": float(finite_age_ms.quantile(0.50)) if not finite_age_ms.empty else 0.0,
            "p95_ms": float(finite_age_ms.quantile(0.95)) if not finite_age_ms.empty else 0.0,
            "max_ms": float(finite_age_ms.max()) if not finite_age_ms.empty else 0.0,
        }
        _add(
            rows,
            "trade_book_alignment_age_ms",
            "warn" if stale_stats["max_ms"] > config.stale_book_warn_ms else "ok",
            stale_stats["max_ms"],
            f"backward book alignment age stats={stale_stats}",
        )

    if not data.fundings.empty:
        finite_funding = np.isfinite(data.fundings["funding_rate"].astype(float))
        nonfinite_funding = int((~finite_funding).sum())
        _add(rows, "funding_rate_finite", "error" if nonfinite_funding else "ok", nonfinite_funding, "non-finite funding rates")
        abs_funding = data.fundings.loc[finite_funding, "funding_rate"].astype(float).abs()
        funding_p99 = float(abs_funding.quantile(0.99)) if not abs_funding.empty else 0.0
        funding_max = float(abs_funding.max()) if not abs_funding.empty else 0.0
        _add(
            rows,
            "funding_rate_outliers",
            "warn" if funding_max > config.funding_abs_warn_threshold else "ok",
            funding_max,
            f"absolute funding p99={funding_p99:.8f}, max={funding_max:.8f}",
        )
        gaps = data.fundings["datetime"].diff().dropna().dt.total_seconds()
        max_gap = float(gaps.max()) if not gaps.empty else 0.0
        stale = int((gaps > config.max_funding_staleness_seconds).sum())
        _add(rows, "funding_gaps", "warn" if stale else "ok", max_gap, f"gaps over threshold={stale}")

    for day in sorted(set(data.orderbook["_source_day"])):
        day_rows = data.orderbook[data.orderbook["_source_day"] == day]
        expected_date = pd.Timestamp(day, tz="UTC").date()
        outside = int((day_rows["datetime"].dt.date != expected_date).sum())
        _add(rows, f"day_boundary_{day}", "warn" if outside else "ok", outside, "rows outside source date")

    if data.trades.empty or data.orderbook.empty:
        event_ordering_stats = _empty_event_ordering_sensitivity(data)

    summary = pd.DataFrame(rows)
    warnings = summary.loc[summary["severity"] == "warn", "check"].tolist()
    return AuditResult(
        tick_size=tick_size,
        summary=summary,
        warnings=warnings,
        spread_stats=spread_stats,
        depth_stats=depth_stats,
        event_ordering_stats=event_ordering_stats,
    )


def write_audit_outputs(result: AuditResult, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.summary.to_csv(output / "audit_summary.csv", index=False)
    pd.DataFrame([result.spread_stats]).to_csv(output / "spread_stats.csv", index=False)
    pd.DataFrame([result.depth_stats]).to_csv(output / "depth_stats.csv", index=False)
    pd.DataFrame([result.event_ordering_stats]).to_csv(output / "event_ordering_sensitivity.csv", index=False)


def _empty_event_ordering_sensitivity(data: MarketData) -> dict[str, object]:
    return {
        "book_rows": int(len(data.orderbook)),
        "trade_rows": int(len(data.trades)),
        "trades_with_same_timestamp_book": 0,
        "trades_with_same_timestamp_book_pct": 0.0,
        "book_updates_with_same_timestamp_trade": 0,
        "book_updates_with_same_timestamp_trade_pct": 0.0,
        "default_equal_timestamp_policy": "trade_before_book",
        "sensitivity_policy_to_review": "book_before_trade",
    }


def _event_ordering_sensitivity(data: MarketData) -> dict[str, object]:
    book_times = data.orderbook["datetime"].drop_duplicates()
    trade_times = data.trades["datetime"].drop_duplicates()
    trade_same = data.trades["datetime"].isin(book_times)
    book_same = data.orderbook["datetime"].isin(trade_times)
    trade_rows = int(len(data.trades))
    book_rows = int(len(data.orderbook))
    same_trade_count = int(trade_same.sum())
    same_book_count = int(book_same.sum())
    return {
        "book_rows": book_rows,
        "trade_rows": trade_rows,
        "trades_with_same_timestamp_book": same_trade_count,
        "trades_with_same_timestamp_book_pct": float(same_trade_count / trade_rows * 100.0) if trade_rows else 0.0,
        "book_updates_with_same_timestamp_trade": same_book_count,
        "book_updates_with_same_timestamp_trade_pct": float(same_book_count / book_rows * 100.0) if book_rows else 0.0,
        "default_equal_timestamp_policy": "trade_before_book",
        "sensitivity_policy_to_review": "book_before_trade",
    }
