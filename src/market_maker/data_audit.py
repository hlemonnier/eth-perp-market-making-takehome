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

    @property
    def passed(self) -> bool:
        return not any(row["severity"] == "error" for _, row in self.summary.iterrows())


def _add(rows: list[dict[str, object]], check: str, severity: str, value: object, detail: str) -> None:
    rows.append({"check": check, "severity": severity, "value": value, "detail": detail})


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
        dup_rows = int(df.duplicated().sum())
        _add(rows, f"{name}_duplicate_rows", "warn" if dup_rows else "ok", dup_rows, "exact duplicate rows")
        dup_times = int(df["datetime"].duplicated().sum())
        _add(rows, f"{name}_duplicate_timestamps", "warn" if dup_times else "ok", dup_times, "duplicate timestamps")

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

    depth_stats: dict[str, float] = {}
    for levels in [1, 5, 10, 20]:
        bid_depth = bid_qty.iloc[:, :levels].sum(axis=1)
        ask_depth = ask_qty.iloc[:, :levels].sum(axis=1)
        depth_stats[f"bid_depth_{levels}_p50"] = float(bid_depth.quantile(0.5))
        depth_stats[f"ask_depth_{levels}_p50"] = float(ask_depth.quantile(0.5))
    _add(rows, "depth_distribution", "ok", depth_stats["bid_depth_1_p50"], f"stats={depth_stats}")

    if not data.trades.empty and not data.orderbook.empty:
        aligned = pd.merge_asof(
            data.trades[["datetime", "price", "is_maker_ask"]].sort_values("datetime"),
            data.orderbook[["datetime", "bid_price_1", "ask_price_1"]].sort_values("datetime"),
            on="datetime",
            direction="backward",
        )
        tolerance = config.trade_alignment_tolerance_ticks * tick_size
        buy_bad = (aligned["is_maker_ask"] == 1) & (aligned["price"] < aligned["ask_price_1"] - tolerance)
        sell_bad = (aligned["is_maker_ask"] == 0) & (aligned["price"] > aligned["bid_price_1"] + tolerance)
        bad_alignment = int((buy_bad | sell_bad).fillna(False).sum())
        severity = "warn" if bad_alignment else "ok"
        _add(rows, "trade_book_alignment", severity, bad_alignment, "trades not near matching side of BBO")

    if not data.fundings.empty:
        gaps = data.fundings["datetime"].diff().dropna().dt.total_seconds()
        max_gap = float(gaps.max()) if not gaps.empty else 0.0
        stale = int((gaps > config.max_funding_staleness_seconds).sum())
        _add(rows, "funding_gaps", "warn" if stale else "ok", max_gap, f"gaps over threshold={stale}")

    for day in sorted(set(data.orderbook["_source_day"])):
        day_rows = data.orderbook[data.orderbook["_source_day"] == day]
        expected_date = pd.Timestamp(day, tz="UTC").date()
        outside = int((day_rows["datetime"].dt.date != expected_date).sum())
        _add(rows, f"day_boundary_{day}", "warn" if outside else "ok", outside, "rows outside source date")

    summary = pd.DataFrame(rows)
    warnings = summary.loc[summary["severity"] == "warn", "check"].tolist()
    return AuditResult(tick_size=tick_size, summary=summary, warnings=warnings, spread_stats=spread_stats, depth_stats=depth_stats)


def write_audit_outputs(result: AuditResult, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.summary.to_csv(output / "audit_summary.csv", index=False)
    pd.DataFrame([result.spread_stats]).to_csv(output / "spread_stats.csv", index=False)
    pd.DataFrame([result.depth_stats]).to_csv(output / "depth_stats.csv", index=False)
