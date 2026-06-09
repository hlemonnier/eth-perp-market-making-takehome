from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path

import pandas as pd
import yaml

from market_maker.config import BacktestConfig
from market_maker.data_audit import AuditResult
from market_maker.simulator import BacktestResult


def write_outputs(
    result: BacktestResult,
    audit: AuditResult,
    config: BacktestConfig,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plots = output / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    result.equity_curve.to_csv(output / "equity_curve.csv", index=False)
    result.fills.to_csv(output / "fills.csv", index=False)
    result.orders.to_csv(output / "orders.csv", index=False)
    result.metrics.overall.to_csv(output / "summary.csv", index=False)
    result.metrics.daily.to_csv(output / "daily_pnl.csv", index=False)
    result.metrics.fill_stats.to_csv(output / "fill_stats.csv", index=False)
    result.metrics.order_stats.to_csv(output / "order_stats.csv", index=False)
    result.metrics.order_cancel_reasons.to_csv(output / "order_cancel_reasons.csv", index=False)
    result.metrics.inventory_stats.to_csv(output / "inventory_stats.csv", index=False)
    result.metrics.realized_spread.to_csv(output / "realized_spread.csv", index=False)
    _fill_diagnostic_breakdowns(result.fills).to_csv(output / "fill_diagnostics.csv", index=False)
    round_trips = round_trip_diagnostics(result.fills)
    round_trips.to_csv(output / "round_trips.csv", index=False)
    round_trip_summary(round_trips).to_csv(output / "round_trip_summary.csv", index=False)
    holding_time_distribution(round_trips).to_csv(output / "holding_time_distribution.csv", index=False)
    _fee_sensitivity(overall=result.metrics.overall).to_csv(output / "fee_sensitivity.csv", index=False)
    pd.DataFrame([audit.event_ordering_stats]).to_csv(output / "event_ordering_exposure.csv", index=False)
    _write_config_snapshot(config, output)

    _plot_equity(result.equity_curve, plots / "equity_curve.png")
    _plot_inventory(result.equity_curve, plots / "inventory.png")
    _plot_spread_histogram(result.equity_curve, plots / "spread_histogram.png")
    _plot_funding_inventory(result.equity_curve, plots / "funding_inventory.png")
    _plot_fills(result.equity_curve, result.fills, plots / "fills_on_mid.png")

    report = build_markdown_report(result, audit, config)
    output.mkdir(parents=True, exist_ok=True)
    (output / "final_report.md").write_text(report)


def build_markdown_report(result: BacktestResult, audit: AuditResult, config: BacktestConfig) -> str:
    overall = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
    interpretation = _interpretation(overall, result.metrics.realized_spread, result.metrics.fill_stats, result.metrics.inventory_stats)
    report_provenance = _report_provenance()
    audit_issue_rows = audit.summary.loc[audit.summary["severity"] != "ok"].copy()
    round_trips = round_trip_diagnostics(result.fills)
    round_trip_stats = round_trip_summary(round_trips)
    lines = [
        "# ETH Perpetual Market-Making Backtest",
        "",
        "## Headline",
        "",
        "This is a simulator-validation baseline, not evidence of a proven profitable market-making strategy. Conservative fills are sparse, simple/aggressive fills expose adverse selection, and mark-to-market inventory can dominate headline PnL.",
        "",
        "## Assumptions",
        "",
        "- Strategy is maker-only and keeps at most one bid and one ask live.",
        f"- Fill model: `{config.execution.fill_model}`.",
        f"- Maker fee assumption: `{config.execution.maker_fee_bps}` bps.",
        f"- Latency assumption: `{config.execution.latency_ms}` ms.",
        f"- Funding accrual uses latest known funding over `{config.execution.funding_period_hours}` hour periods; positive funding is assumed to mean longs pay shorts.",
        f"- Inferred tick size: `{audit.tick_size}`.",
        f"- Cancel latency assumption: `{config.execution.cancel_latency_ms if config.execution.cancel_latency_ms is not None else config.execution.latency_ms}` ms.",
        f"- Queue depletion fraction: `{config.execution.queue_depletion_fraction}`.",
        f"- Forced-flat slippage: `{config.execution.force_flat_slippage_bps}` bps.",
        f"- Forced-flat closing fee: `{config.execution.force_flat_fee_bps if config.execution.force_flat_fee_bps is not None else config.execution.maker_fee_bps}` bps.",
        "- Equal-timestamp policy: `trade_before_book` by default; reproduction outputs include an alternate `book_before_trade` policy check.",
        "- End inventory is reported three ways: mid-marked total PnL, bid/ask liquidation-adjusted PnL, and forced-flat PnL after configured slippage and closing fee.",
        f"- Report provenance: `{report_provenance}`.",
        "",
        "## Audit Summary",
        "",
        f"- Audit passed: `{audit.passed}`.",
        f"- Warning checks: `{', '.join(audit.warnings) if audit.warnings else 'none'}`.",
        "",
        "### Audit Check Details",
        "",
        _markdown_table(audit.summary, max_rows=100),
        "",
        "### Audit Warning/Error Details",
        "",
        _markdown_table(audit_issue_rows, max_rows=100),
        "",
        "### Event Ordering Exposure",
        "",
        "The default simulator policy processes trades before book updates when timestamps are exactly equal. Audit output quantifies exposure to the alternate book-before-trade convention; reproduce workflows also write `event_ordering_sensitivity.csv` with actual default-vs-alternate backtests.",
        "",
        _markdown_table(pd.DataFrame([audit.event_ordering_stats])),
        "",
        "### Spread Statistics",
        "",
        _markdown_table(pd.DataFrame([audit.spread_stats])),
        "",
        "### Depth Statistics",
        "",
        _markdown_table(pd.DataFrame([audit.depth_stats])),
        "",
        "## Strategy",
        "",
        "Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, fee-aware expected-edge gates, book-imbalance adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior. Pressure and expected-edge stops are enforced at simulator level on existing live orders; fills during cancel latency are explicitly flagged.",
        "",
        "## Results",
        "",
    ]
    if overall:
        for key, value in overall.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No equity results produced.")
    lines += [
        "",
        "## Daily PnL",
        "",
        _markdown_table(result.metrics.daily),
        "",
        "## Round-Trip And Holding-Time Diagnostics",
        "",
        "Rows pair fills greedily when inventory is reduced by an opposite-side fill. Long holding periods indicate inventory-path PnL rather than clean high-frequency spread economics.",
        "",
        "### Round-Trip Concentration Summary",
        "",
        _markdown_table(round_trip_stats),
        "",
        "### Round-Trip Detail",
        "",
        _markdown_table(round_trips, max_rows=20),
        "",
        "### Holding-Time Distribution",
        "",
        _markdown_table(holding_time_distribution(round_trips)),
        "",
        "## Fill Statistics",
        "",
        _markdown_table(result.metrics.fill_stats),
        "",
        "### Fill Diagnostic Breakdowns",
        "",
        _markdown_table(_fill_diagnostic_breakdowns(result.fills), max_rows=60),
        "",
        "## Order Statistics",
        "",
        _markdown_table(result.metrics.order_stats),
        "",
        "### Order Cancellation Reasons",
        "",
        _markdown_table(result.metrics.order_cancel_reasons, max_rows=100),
        "",
        "## Inventory Statistics",
        "",
        _markdown_table(result.metrics.inventory_stats),
        "",
        "## Realized Spread and Adverse Selection",
        "",
        "Realized-spread horizons use event-level book marks computed during the simulation; if those marks are unavailable, the metrics are explicitly labeled as sampled-equity-curve marks. The lookup-lag columns report the delay from each target horizon to the next observed mark.",
        "",
        _markdown_table(result.metrics.realized_spread),
        "",
        "## Maker Fee/Rebate Sensitivity",
        "",
        _markdown_table(_fee_sensitivity(result.metrics.overall)),
        "",
        "## Known Limitations",
        "",
        "- The implemented strategy is simple and not proven profitable; use the run as simulator validation and diagnostics, not as evidence of robust market-making edge.",
        "- The conservative queue model likely underfills because L2 snapshots and prints do not reveal cancellations ahead of our simulated order; use `partial_queue`/`calibrated_queue` queue-depletion sweeps as robustness checks.",
        "- The simple fill model is intentionally aggressive and stress-tests adverse selection and inventory-directional risk; positive simple-fill PnL is not alpha evidence when it comes from carrying directional inventory.",
        "- Order churn remains high relative to fills; fill/order ratios, cancel/order ratios, and cancellation reasons should be read as diagnostics rather than optimized execution policy.",
        "- The included dataset covers only three days, so fill counts, drawdown, and PnL are not statistically reliable strategy-performance estimates.",
        "",
        "## Conclusion",
        "",
        interpretation,
        "",
        "",
        "## Output Files",
        "",
        "- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`",
        "- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`",
        "- `fill_stats.csv`, `order_stats.csv`, `order_cancel_reasons.csv`, `inventory_stats.csv`, `realized_spread.csv`, `round_trips.csv`, `round_trip_summary.csv`, `holding_time_distribution.csv`, `fee_sensitivity.csv`, `event_ordering_exposure.csv`",
        "- Reproduction suite roots also include `fill_model_comparison.csv`, `event_ordering_sensitivity.csv`, and `run_scope.csv`.",
        "- `config_used.yaml`",
        "- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`",
        "",
        "## Interpretation Discipline",
        "",
        "Use the PnL decomposition rather than total PnL alone. Positive round-trip PnL with negative short-horizon realized spreads should be read as inventory-path PnL, not clean spread economics. Overall and daily max drawdown are event-level diagnostics; sampled 1-minute drawdown remains in the tables for comparison. The Sharpe-like metric is a short-sample diagnostic only, not a statistically reliable Sharpe estimate.",
    ]
    return "\n".join(lines) + "\n"


def _write_config_snapshot(config: BacktestConfig, output: Path) -> None:
    raw = asdict(config)
    raw["data"]["data_dir"] = str(raw["data"]["data_dir"])
    raw["report_provenance"] = _report_provenance()
    (output / "config_used.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))


def _fee_sensitivity(overall: pd.DataFrame, bps_values: tuple[float, ...] = (-0.5, 0.0, 0.5, 1.0)) -> pd.DataFrame:
    if overall.empty:
        return pd.DataFrame(
            columns=[
                "maker_fee_bps",
                "estimated_fees",
                "estimated_total_pnl",
                "estimated_realized_pnl",
                "max_drawdown",
                "fills",
                "turnover_usd",
                "estimated_pnl_per_turnover",
            ]
        )
    row = overall.iloc[0]
    turnover = float(row.get("turnover_usd", 0.0))
    total_pnl = float(row.get("total_pnl", 0.0))
    realized_pnl = float(row.get("realized_trading_pnl", 0.0))
    current_fees = float(row.get("fees", 0.0))
    pre_fee_pnl = total_pnl + current_fees
    records = []
    for maker_fee_bps in bps_values:
        estimated_fees = turnover * maker_fee_bps / 10_000.0
        estimated_total_pnl = pre_fee_pnl - estimated_fees
        estimated_realized_pnl = realized_pnl - estimated_fees
        records.append(
            {
                "maker_fee_bps": maker_fee_bps,
                "estimated_fees": estimated_fees,
                "estimated_total_pnl": estimated_total_pnl,
                "estimated_realized_pnl": estimated_realized_pnl,
                "max_drawdown": float(row.get("max_drawdown", 0.0)),
                "fills": int(float(row.get("total_fills", 0.0))),
                "turnover_usd": turnover,
                "estimated_pnl_per_turnover": estimated_total_pnl / turnover if turnover else 0.0,
            }
        )
    return pd.DataFrame(records)


def _fill_diagnostic_breakdowns(fills: pd.DataFrame) -> pd.DataFrame:
    columns = ["breakdown", "bucket", "fills", "avg_realized_spread_5s", "avg_markout_1s", "avg_quote_age_ms"]
    if fills.empty:
        return pd.DataFrame(columns=columns)
    df = fills.copy()
    specs = {
        "side": df["side"] if "side" in df.columns else pd.Series("unknown", index=df.index),
        "pressure_bucket": pd.cut(
            _numeric_series(df, "pressure_at_fill"),
            bins=[-1.01, -0.75, -0.50, -0.25, 0.25, 0.50, 0.75, 1.01],
            include_lowest=True,
        ),
        "quote_age_bucket_ms": pd.cut(
            _numeric_series(df, "quote_age_ms"),
            bins=[-0.1, 250, 1000, 5000, 30000, float("inf")],
            labels=["0-250", "250-1000", "1000-5000", "5000-30000", "30000+"],
        ),
        "queue_ahead_bucket": pd.cut(
            _numeric_series(df, "queue_ahead_initial"),
            bins=[-0.1, 0, 1, 5, 20, float("inf")],
            labels=["0", "0-1", "1-5", "5-20", "20+"],
        ),
        "inventory_bucket": pd.cut(
            _numeric_series(df, "inventory_before"),
            bins=[-float("inf"), -0.5, -0.05, 0.05, 0.5, float("inf")],
            labels=["short_large", "short_small", "flat", "long_small", "long_large"],
        ),
        "spread_bucket": pd.cut(
            _numeric_series(df, "spread_at_fill"),
            bins=[-0.1, 0.1, 0.5, 1.0, 2.0, float("inf")],
            labels=["<=0.1", "0.1-0.5", "0.5-1", "1-2", "2+"],
        ),
    }
    rows = []
    for breakdown, labels in specs.items():
        temp = df.assign(_bucket=labels.astype("string").fillna("missing"))
        grouped = temp.groupby("_bucket", dropna=False)
        for bucket, group in grouped:
            rows.append(
                {
                    "breakdown": breakdown,
                    "bucket": str(bucket),
                    "fills": int(len(group)),
                    "avg_realized_spread_5s": _safe_mean(group.get("realized_spread_5s")),
                    "avg_markout_1s": _safe_mean(group.get("markout_1s")),
                    "avg_quote_age_ms": _safe_mean(group.get("quote_age_ms")),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def round_trip_diagnostics(fills: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "entry_time",
        "exit_time",
        "entry_side",
        "exit_side",
        "quantity",
        "entry_price",
        "exit_price",
        "holding_seconds",
        "roundtrip_pnl",
        "exit_order_status",
    ]
    if fills.empty or not {"timestamp", "side", "price", "quantity"}.issubset(fills.columns):
        return pd.DataFrame(columns=columns)
    lots: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for _, fill in fills.sort_values("timestamp").iterrows():
        side = str(fill["side"])
        direction = 1 if side == "bid" else -1
        remaining = float(fill["quantity"])
        while remaining > 1e-12 and lots and int(lots[0]["direction"]) != direction:
            lot = lots[0]
            quantity = min(remaining, float(lot["quantity"]))
            entry_time = pd.Timestamp(lot["timestamp"])
            exit_time = pd.Timestamp(fill["timestamp"])
            entry_price = float(lot["price"])
            exit_price = float(fill["price"])
            entry_direction = int(lot["direction"])
            roundtrip_pnl = (exit_price - entry_price) * quantity if entry_direction > 0 else (entry_price - exit_price) * quantity
            rows.append(
                {
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_side": lot["side"],
                    "exit_side": side,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "holding_seconds": max(0.0, (exit_time - entry_time).total_seconds()),
                    "roundtrip_pnl": roundtrip_pnl,
                    "exit_order_status": fill.get("order_status_at_fill", ""),
                }
            )
            remaining -= quantity
            lot["quantity"] = float(lot["quantity"]) - quantity
            if float(lot["quantity"]) <= 1e-12:
                lots.pop(0)
        if remaining > 1e-12:
            lots.append(
                {
                    "timestamp": fill["timestamp"],
                    "side": side,
                    "direction": direction,
                    "quantity": remaining,
                    "price": float(fill["price"]),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def round_trip_summary(round_trips: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "closed_round_trips",
        "total_roundtrip_pnl",
        "positive_roundtrip_pnl",
        "negative_roundtrip_pnl",
        "top_roundtrip_pnl",
        "top_roundtrip_pnl_share_pct",
        "top_abs_roundtrip_pnl_share_pct",
        "median_holding_seconds",
        "p90_holding_seconds",
        "max_holding_seconds",
    ]
    if round_trips.empty or "roundtrip_pnl" not in round_trips.columns:
        return pd.DataFrame([{column: 0.0 for column in columns}])
    pnl = pd.to_numeric(round_trips["roundtrip_pnl"], errors="coerce").dropna()
    holding = pd.to_numeric(round_trips.get("holding_seconds", pd.Series(dtype=float)), errors="coerce").dropna()
    if pnl.empty:
        return pd.DataFrame([{column: 0.0 for column in columns}])
    positive_pnl = pnl[pnl > 0].sum()
    negative_pnl = pnl[pnl < 0].sum()
    total_pnl = pnl.sum()
    top_pnl = pnl.max()
    abs_sum = pnl.abs().sum()
    top_abs_share = pnl.abs().max() / abs_sum * 100.0 if abs_sum else 0.0
    top_share = top_pnl / positive_pnl * 100.0 if positive_pnl > 0 else 0.0
    return pd.DataFrame(
        [
            {
                "closed_round_trips": int(len(pnl)),
                "total_roundtrip_pnl": float(total_pnl),
                "positive_roundtrip_pnl": float(positive_pnl),
                "negative_roundtrip_pnl": float(negative_pnl),
                "top_roundtrip_pnl": float(top_pnl),
                "top_roundtrip_pnl_share_pct": float(top_share),
                "top_abs_roundtrip_pnl_share_pct": float(top_abs_share),
                "median_holding_seconds": float(holding.median()) if not holding.empty else 0.0,
                "p90_holding_seconds": float(holding.quantile(0.90)) if not holding.empty else 0.0,
                "max_holding_seconds": float(holding.max()) if not holding.empty else 0.0,
            }
        ],
        columns=columns,
    )


def holding_time_distribution(round_trips: pd.DataFrame) -> pd.DataFrame:
    columns = ["holding_time_bucket", "round_trips", "total_roundtrip_pnl", "average_roundtrip_pnl"]
    if round_trips.empty or "holding_seconds" not in round_trips.columns:
        return pd.DataFrame(columns=columns)
    table = round_trips.copy()
    table["holding_seconds"] = pd.to_numeric(table["holding_seconds"], errors="coerce")
    table["roundtrip_pnl"] = pd.to_numeric(table.get("roundtrip_pnl", 0.0), errors="coerce").fillna(0.0)
    table = table.dropna(subset=["holding_seconds"])
    if table.empty:
        return pd.DataFrame(columns=columns)
    table["holding_time_bucket"] = pd.cut(
        table["holding_seconds"],
        bins=[-0.1, 60, 300, 1800, 3600, 14_400, 43_200, float("inf")],
        labels=["0-1m", "1-5m", "5-30m", "30-60m", "1-4h", "4-12h", "12h+"],
    )
    grouped = (
        table.groupby("holding_time_bucket", observed=False)
        .agg(round_trips=("roundtrip_pnl", "count"), total_roundtrip_pnl=("roundtrip_pnl", "sum"), average_roundtrip_pnl=("roundtrip_pnl", "mean"))
        .reset_index()
    )
    grouped["holding_time_bucket"] = grouped["holding_time_bucket"].astype(str)
    return grouped[columns]


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NA, index=df.index)
    return pd.to_numeric(df[column], errors="coerce")


def _safe_mean(values: pd.Series | None) -> float:
    if values is None:
        return 0.0
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return 0.0
    return float(numeric.mean())


def _report_provenance() -> str:
    return os.environ.get("MM_REPORT_PROVENANCE") or os.environ.get("REPORT_BUILD_ID", "not embedded")


def _markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    shown = df.head(max_rows).copy()
    headers = list(shown.columns)
    rows = []
    for _, row in shown.iterrows():
        rows.append([_format_cell(row[col]) for col in headers])
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    suffix = []
    if len(df) > max_rows:
        suffix.append(f"\n_Showing {max_rows} of {len(df)} rows._")
    return "\n".join([header_line, separator, *body, *suffix])


def _format_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _interpretation(
    overall: dict[str, object],
    realized_spread: pd.DataFrame,
    fill_stats: pd.DataFrame,
    inventory_stats: pd.DataFrame,
) -> str:
    if not overall:
        return "No backtest result was produced."
    total = float(overall.get("total_pnl", 0.0))
    forced_flat = float(overall.get("forced_flat_pnl", overall.get("liquidation_adjusted_pnl", total)))
    realized = float(overall.get("realized_trading_pnl", 0.0))
    unrealized = float(overall.get("unrealized_trading_pnl", 0.0))
    funding = float(overall.get("funding_pnl", 0.0))
    fills = int(float(overall.get("total_fills", 0.0)))
    drawdown = float(overall.get("max_drawdown", 0.0))
    parts = [
        f"The run finished with mid-marked total PnL `{total:.4f}` USD, forced-flat PnL `{forced_flat:.4f}` USD, realized trading PnL `{realized:.4f}` USD, unrealized trading PnL `{unrealized:.4f}` USD, and funding PnL `{funding:.4f}` USD.",
        f"The strategy generated `{fills}` fills and max drawdown `{drawdown:.4f}` USD under the selected fill model.",
    ]
    if fills <= 10:
        parts.append("Fill count is sparse and too small to support a statistically meaningful performance claim.")
    realized_spread_values = pd.Series(dtype=float)
    if not realized_spread.empty and "average_realized_spread" in realized_spread.columns:
        realized_spread_values = pd.to_numeric(realized_spread["average_realized_spread"], errors="coerce").dropna()
    pending_cancel_fills = 0
    if not fill_stats.empty and "pending_cancel_fills" in fill_stats.columns:
        pending_cancel_fills = int(float(fill_stats.iloc[0].get("pending_cancel_fills", 0)))
    pct_short = 0.0
    if not inventory_stats.empty and "pct_short" in inventory_stats.columns:
        pct_short = float(inventory_stats.iloc[0].get("pct_short", 0.0))
    if abs(unrealized) > max(abs(realized) * 3.0, 1.0):
        parts.append(
            "Most reported PnL is mark-to-market inventory PnL, so the result should be treated as inventory-path exposure inside a simulator validation, not proof of robust market-making edge."
        )
    elif realized > 0 and not realized_spread_values.empty and (realized_spread_values < 0).any():
        parts.append(
            "Realized round-trip PnL is positive, but short-horizon realized-spread markouts are negative; do not interpret this as clean spread capture."
        )
    elif realized > 0:
        parts.append(
            "Realized round-trip PnL is positive, but that alone is not clean spread-capture evidence; use the realized-spread markouts, fill count, and inventory path before making any profitability claim."
        )
    if pending_cancel_fills:
        parts.append(f"`{pending_cancel_fills}` fills occurred while cancellation was pending, so cancel-latency adverse selection remains a key diagnostic.")
    if pct_short > 75.0:
        parts.append(f"The run is short `{pct_short:.2f}%` of sampled time, so positive PnL may reflect directional inventory exposure.")
    if realized <= 0:
        parts.append("Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.")
    return " ".join(parts)


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _plot_equity(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity["timestamp"], equity["equity"], linewidth=1)
    ax.set_title("Equity Curve")
    ax.set_ylabel("USD")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_inventory(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity["timestamp"], equity["inventory"], linewidth=1)
    ax.set_title("Inventory")
    ax.set_ylabel("ETH")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_spread_histogram(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    equity["spread"].dropna().hist(ax=ax, bins=80)
    ax.set_title("Spread Distribution")
    ax.set_xlabel("USD")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_funding_inventory(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    plt = _pyplot()
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(equity["timestamp"], equity["inventory"], linewidth=1, label="Inventory")
    ax1.set_ylabel("Inventory ETH")
    ax2 = ax1.twinx()
    ax2.plot(equity["timestamp"], equity["funding_rate"], linewidth=0.8, color="tab:orange", label="Funding")
    ax2.set_ylabel("Funding rate")
    ax1.set_title("Funding Rate and Inventory")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_fills(equity: pd.DataFrame, fills: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(10, 4))
    sampled = equity.iloc[:: max(1, len(equity) // 50_000)]
    ax.plot(sampled["timestamp"], sampled["mid"], linewidth=0.8, label="Mid")
    if not fills.empty:
        bids = fills[fills["side"] == "bid"]
        asks = fills[fills["side"] == "ask"]
        ax.scatter(bids["timestamp"], bids["price"], s=8, label="Buy fills", alpha=0.7)
        ax.scatter(asks["timestamp"], asks["price"], s=8, label="Sell fills", alpha=0.7)
    ax.set_title("Fills on Mid Price")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
