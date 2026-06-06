from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class MetricsBundle:
    overall: pd.DataFrame
    daily: pd.DataFrame
    fill_stats: pd.DataFrame
    order_stats: pd.DataFrame
    inventory_stats: pd.DataFrame
    realized_spread: pd.DataFrame
    order_cancel_reasons: pd.DataFrame = field(default_factory=pd.DataFrame)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    drawdown = equity - equity.cummax()
    return float(-drawdown.min())


def sharpe_like_1m(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty:
        return 0.0
    curve = equity_curve.set_index("timestamp").sort_index()
    resampled = curve["equity"].resample("1min").last().ffill()
    pnl = resampled.diff().dropna()
    if len(pnl) < 2 or pnl.std(ddof=1) == 0:
        return 0.0
    return float(np.sqrt(1440.0) * pnl.mean() / pnl.std(ddof=1))


def daily_summary(equity_curve: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame()
    curve = equity_curve.copy()
    curve["date"] = curve["timestamp"].dt.date.astype(str)
    rows = []
    previous_end = 0.0
    previous_realized = 0.0
    previous_unrealized = 0.0
    previous_funding = 0.0
    previous_fees = 0.0
    for date, day in curve.groupby("date", sort=True):
        day_fills = fills[fills["timestamp"].dt.date.astype(str) == date] if not fills.empty else pd.DataFrame()
        start_equity = previous_end
        end_equity = float(day["equity"].iloc[-1])
        end_realized = float(day["realized_trading_pnl"].iloc[-1])
        end_unrealized = float(day["unrealized_trading_pnl"].iloc[-1])
        end_funding = float(day["funding_pnl"].iloc[-1])
        end_fees = float(day["fees"].iloc[-1])
        previous_end = end_equity
        rows.append(
            {
                "date": date,
                "starting_equity": start_equity,
                "ending_equity": end_equity,
                "daily_pnl": end_equity - start_equity,
                "daily_realized_trading_pnl": end_realized - previous_realized,
                "daily_unrealized_trading_pnl_change": end_unrealized - previous_unrealized,
                "daily_funding_pnl": end_funding - previous_funding,
                "daily_fees": end_fees - previous_fees,
                "ending_realized_trading_pnl": end_realized,
                "ending_unrealized_trading_pnl": end_unrealized,
                "ending_funding_pnl": end_funding,
                "ending_fees": end_fees,
                "bid_fills": int((day_fills["side"] == "bid").sum()) if not day_fills.empty else 0,
                "ask_fills": int((day_fills["side"] == "ask").sum()) if not day_fills.empty else 0,
                "bid_volume_eth": float(day_fills.loc[day_fills["side"] == "bid", "quantity"].sum()) if not day_fills.empty else 0.0,
                "ask_volume_eth": float(day_fills.loc[day_fills["side"] == "ask", "quantity"].sum()) if not day_fills.empty else 0.0,
                "average_inventory": float(day["inventory"].mean()),
                "max_abs_inventory": float(day["inventory"].abs().max()),
                "max_drawdown": max_drawdown(day["equity"]),
            }
        )
        previous_realized = end_realized
        previous_unrealized = end_unrealized
        previous_funding = end_funding
        previous_fees = end_fees
    return pd.DataFrame(rows)


def realized_spread_stats(fills: pd.DataFrame, equity_curve: pd.DataFrame, mark_curve: pd.DataFrame | None = None) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame()
    mark_source = "event_level_book"
    if mark_curve is not None and not mark_curve.empty:
        curve = mark_curve[["timestamp", "mid"]].dropna().sort_values("timestamp").rename(columns={"timestamp": "mark_timestamp"})
    elif not equity_curve.empty:
        curve = equity_curve[["timestamp", "mid"]].dropna().sort_values("timestamp").rename(columns={"timestamp": "mark_timestamp"})
        mark_source = "sampled_equity_curve"
    else:
        return pd.DataFrame()
    rows = []
    for horizon in [1, 5, 30]:
        future = curve.copy()
        future["lookup_time"] = future["mark_timestamp"]
        fill_lookup = fills.copy()
        fill_lookup["lookup_time"] = fill_lookup["timestamp"] + pd.Timedelta(seconds=horizon)
        aligned = pd.merge_asof(
            fill_lookup.sort_values("lookup_time"),
            future[["lookup_time", "mark_timestamp", "mid"]].sort_values("lookup_time"),
            on="lookup_time",
            direction="forward",
        )
        if aligned.empty:
            continue
        aligned = aligned.dropna(subset=["mid", "mid_at_fill"])
        if aligned.empty:
            continue
        sell = aligned["side"] == "ask"
        realized = np.where(sell, aligned["price"] - aligned["mid"], aligned["mid"] - aligned["price"])
        toxicity = np.where(sell, aligned["mid"] - aligned["mid_at_fill"], aligned["mid_at_fill"] - aligned["mid"])
        lookup_lag_ms = (aligned["mark_timestamp"] - aligned["lookup_time"]).dt.total_seconds() * 1000.0
        rows.append(
            {
                "horizon_seconds": horizon,
                "mark_source": mark_source,
                "marks_available": int(len(curve)),
                "average_realized_spread": float(np.nanmean(realized)),
                "average_toxicity": float(np.nanmean(toxicity)),
                "median_mark_lookup_lag_ms": float(lookup_lag_ms.median()) if not lookup_lag_ms.empty else 0.0,
                "max_mark_lookup_lag_ms": float(lookup_lag_ms.max()) if not lookup_lag_ms.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_metrics(
    equity_curve: pd.DataFrame,
    fills: pd.DataFrame,
    orders: pd.DataFrame,
    final_liquidation_adjusted_equity: float,
    event_max_drawdown_loss: float | None = None,
    mark_curve: pd.DataFrame | None = None,
) -> MetricsBundle:
    if equity_curve.empty:
        empty = pd.DataFrame()
        return MetricsBundle(empty, empty, empty, empty, empty, empty)

    final = equity_curve.iloc[-1]
    total_fill_volume = float(fills["quantity"].sum()) if not fills.empty else 0.0
    turnover = float((fills["quantity"] * fills["price"]).sum()) if not fills.empty else 0.0
    overall = pd.DataFrame(
        [
            {
                "total_pnl": float(final["equity"]),
                "realized_trading_pnl": float(final["realized_trading_pnl"]),
                "unrealized_trading_pnl": float(final["unrealized_trading_pnl"]),
                "funding_pnl": float(final["funding_pnl"]),
                "fees": float(final["fees"]),
                "liquidation_adjusted_pnl": final_liquidation_adjusted_equity,
                "total_fills": int(len(fills)),
                "fill_volume_eth": total_fill_volume,
                "turnover_usd": turnover,
                "max_inventory": float(equity_curve["inventory"].max()),
                "min_inventory": float(equity_curve["inventory"].min()),
                "mean_abs_inventory": float(equity_curve["inventory"].abs().mean()),
                "max_drawdown": float(event_max_drawdown_loss) if event_max_drawdown_loss is not None else max_drawdown(equity_curve["equity"]),
                "sampled_1m_max_drawdown": max_drawdown(equity_curve["equity"]),
                "sharpe_like_1m": sharpe_like_1m(equity_curve),
                "pnl_per_turnover": float(final["equity"] / turnover) if turnover else 0.0,
                "pnl_per_eth": float(final["equity"] / total_fill_volume) if total_fill_volume else 0.0,
            }
        ]
    )

    if fills.empty:
        fill_stats = pd.DataFrame()
    else:
        passive_edge = np.where(
            fills["side"] == "ask",
            fills["price"] - fills["mid_at_fill"],
            fills["mid_at_fill"] - fills["price"],
        )
        fill_stats = pd.DataFrame(
            [
                {
                    "fill_count": int(len(fills)),
                    "fill_volume_eth": total_fill_volume,
                    "bid_fills": int((fills["side"] == "bid").sum()),
                    "ask_fills": int((fills["side"] == "ask").sum()),
                    "mean_fill_size": float(fills["quantity"].mean()),
                    "median_fill_size": float(fills["quantity"].median()),
                    "average_fill_notional": float((fills["quantity"] * fills["price"]).mean()),
                    "average_passive_edge_to_mid": float(np.nanmean(passive_edge)),
                }
            ]
        )

    order_stats = summarize_orders(orders, fills)
    order_cancel_reasons = summarize_order_cancel_reasons(orders)

    inventory = equity_curve["inventory"]
    inventory_stats = pd.DataFrame(
        [
            {
                "mean_inventory": float(inventory.mean()),
                "mean_abs_inventory": float(inventory.abs().mean()),
                "std_inventory": float(inventory.std(ddof=1)) if len(inventory) > 1 else 0.0,
                "min_inventory": float(inventory.min()),
                "max_inventory": float(inventory.max()),
                "pct_long": float((inventory > 0).mean() * 100.0),
                "pct_short": float((inventory < 0).mean() * 100.0),
                "pct_flat": float((inventory.abs() <= 1e-12).mean() * 100.0),
            }
        ]
    )

    return MetricsBundle(
        overall=overall,
        daily=daily_summary(equity_curve, fills),
        fill_stats=fill_stats,
        order_stats=order_stats,
        inventory_stats=inventory_stats,
        realized_spread=realized_spread_stats(fills, equity_curve, mark_curve),
        order_cancel_reasons=order_cancel_reasons,
    )


def summarize_orders(orders: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            [
                {
                    "placed_orders": 0,
                    "filled_orders": 0,
                    "cancelled_orders": 0,
                    "resized_orders": 0,
                    "fill_to_order_ratio": 0.0,
                    "filled_order_ratio": 0.0,
                    "cancel_to_order_ratio": 0.0,
                    "top_cancel_reason": "",
                    "top_cancel_reason_count": 0,
                    "average_quote_lifetime_seconds": 0.0,
                    "p95_quote_lifetime_seconds": 0.0,
                    "max_quote_lifetime_seconds": 0.0,
                    "cancelled_before_active_orders": 0,
                    "pct_orders_cancelled_before_active": 0.0,
                }
            ]
        )

    placed = orders[orders["event"] == "placed"].copy()
    cancelled = orders[orders["event"] == "cancelled"].copy()
    resized = orders[orders["event"] == "resized"]
    fill_count = len(fills)
    fill_to_order_ratio = fill_count / len(placed) if len(placed) else 0.0
    filled_orders = int(fills["order_id"].nunique()) if not fills.empty and "order_id" in fills.columns else 0
    filled_order_ratio = filled_orders / len(placed) if len(placed) else 0.0
    cancel_to_order_ratio = len(cancelled) / len(placed) if len(placed) else 0.0
    cancel_reason_counts = cancelled["reason"].value_counts() if "reason" in cancelled.columns else pd.Series(dtype=int)
    top_cancel_reason = str(cancel_reason_counts.index[0]) if not cancel_reason_counts.empty else ""
    top_cancel_reason_count = int(cancel_reason_counts.iloc[0]) if not cancel_reason_counts.empty else 0

    lifetimes: list[float] = []
    cancelled_before_active = 0
    if not placed.empty:
        placed_by_id = placed.drop_duplicates("order_id").set_index("order_id")
        terminal_times: dict[object, pd.Timestamp] = {}
        if not fills.empty and {"order_id", "timestamp"}.issubset(fills.columns):
            fill_times = fills.groupby("order_id")["timestamp"].max()
            terminal_times.update({order_id: pd.Timestamp(timestamp) for order_id, timestamp in fill_times.items()})
        if not cancelled.empty:
            cancel_times = cancelled.groupby("order_id")["timestamp"].max()
            for order_id, timestamp in cancel_times.items():
                cancelled_at = pd.Timestamp(timestamp)
                previous_terminal = terminal_times.get(order_id)
                if previous_terminal is None or cancelled_at > previous_terminal:
                    terminal_times[order_id] = cancelled_at

        for order_id, terminal_at in terminal_times.items():
            if order_id not in placed_by_id.index:
                continue
            created = pd.Timestamp(placed_by_id.loc[order_id, "timestamp"])
            lifetimes.append(max(0.0, (terminal_at - created).total_seconds()))

        for _, cancel in cancelled.iterrows():
            order_id = cancel["order_id"]
            if order_id not in placed_by_id.index:
                continue
            active_time = pd.Timestamp(placed_by_id.loc[order_id, "active_time"])
            cancelled_at = pd.Timestamp(cancel["timestamp"])
            if cancelled_at < active_time:
                cancelled_before_active += 1

    return pd.DataFrame(
        [
            {
                "placed_orders": int(len(placed)),
                "filled_orders": filled_orders,
                "cancelled_orders": int(len(cancelled)),
                "resized_orders": int(len(resized)),
                "fill_to_order_ratio": float(fill_to_order_ratio),
                "filled_order_ratio": float(filled_order_ratio),
                "cancel_to_order_ratio": float(cancel_to_order_ratio),
                "top_cancel_reason": top_cancel_reason,
                "top_cancel_reason_count": top_cancel_reason_count,
                "average_quote_lifetime_seconds": float(np.mean(lifetimes)) if lifetimes else 0.0,
                "p95_quote_lifetime_seconds": float(np.percentile(lifetimes, 95)) if lifetimes else 0.0,
                "max_quote_lifetime_seconds": float(np.max(lifetimes)) if lifetimes else 0.0,
                "cancelled_before_active_orders": int(cancelled_before_active),
                "pct_orders_cancelled_before_active": float(cancelled_before_active / len(cancelled) * 100.0) if len(cancelled) else 0.0,
            }
        ]
    )


def summarize_order_cancel_reasons(orders: pd.DataFrame) -> pd.DataFrame:
    columns = ["reason", "cancelled_orders", "cancelled_before_active_orders"]
    if orders.empty or "reason" not in orders.columns:
        return pd.DataFrame(columns=columns)
    cancelled = orders[orders["event"] == "cancelled"].copy()
    if cancelled.empty:
        return pd.DataFrame(columns=columns)
    cancelled["cancelled_before_active"] = pd.to_datetime(cancelled["timestamp"], utc=True) < pd.to_datetime(cancelled["active_time"], utc=True)
    grouped = (
        cancelled.groupby("reason", dropna=False)
        .agg(
            cancelled_orders=("order_id", "count"),
            cancelled_before_active_orders=("cancelled_before_active", "sum"),
        )
        .reset_index()
        .sort_values(["cancelled_orders", "reason"], ascending=[False, True])
    )
    grouped["cancelled_before_active_orders"] = grouped["cancelled_before_active_orders"].astype(int)
    return grouped[columns]
