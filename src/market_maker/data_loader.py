from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from market_maker.book_state import LEVELS


ORDERBOOK_COLUMNS = ["datetime"] + [
    column
    for level in LEVELS
    for column in (
        f"bid_price_{level}",
        f"bid_qty_{level}",
        f"ask_price_{level}",
        f"ask_qty_{level}",
    )
]
TRADE_COLUMNS = ["datetime", "price", "size", "is_maker_ask"]
FUNDING_COLUMNS = ["datetime", "funding_rate"]


@dataclass
class MarketData:
    orderbook: pd.DataFrame
    trades: pd.DataFrame
    fundings: pd.DataFrame


def normalize_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime(series, unit="ns", utc=True)
    return pd.to_datetime(series, utc=True)


def validate_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _load_daily_file(path: Path, required: list[str], label: str, day: str, max_rows: int | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    if max_rows is not None:
        df = df.head(max_rows)
    validate_columns(df, required, str(path))
    df = df.copy(deep=False)
    df["datetime"] = normalize_datetime(df["datetime"])
    df["_source_day"] = day
    df["_row_id"] = np.arange(len(df))
    return _sort_market_frame(df)


def load_market_data(data_dir: str | Path, days: tuple[str, ...] | list[str]) -> MarketData:
    root = Path(data_dir)
    orderbooks: list[pd.DataFrame] = []
    trades: list[pd.DataFrame] = []
    fundings: list[pd.DataFrame] = []
    for day in days:
        orderbooks.append(_load_daily_file(root / "orderbook" / f"{day}.parquet", ORDERBOOK_COLUMNS, "orderbook", day))
        trades.append(_load_daily_file(root / "trades" / f"{day}.parquet", TRADE_COLUMNS, "trades", day))
        fundings.append(_load_daily_file(root / "fundings" / f"{day}.parquet", FUNDING_COLUMNS, "fundings", day))

    return MarketData(
        orderbook=_sort_market_frame(pd.concat(orderbooks, ignore_index=True)),
        trades=_sort_market_frame(pd.concat(trades, ignore_index=True)),
        fundings=_sort_market_frame(pd.concat(fundings, ignore_index=True)),
    )


def load_market_data_sample(
    data_dir: str | Path,
    days: tuple[str, ...] | list[str],
    max_orderbook_rows: int = 50_000,
) -> MarketData:
    if not days:
        raise ValueError("At least one day is required for sample loading.")
    root = Path(data_dir)
    day = str(days[0])
    orderbook = _load_daily_file(root / "orderbook" / f"{day}.parquet", ORDERBOOK_COLUMNS, "orderbook", day, max_rows=max_orderbook_rows)
    if orderbook.empty:
        raise ValueError(f"No orderbook rows loaded for smoke sample day {day}.")
    start = orderbook["datetime"].iloc[0]
    end = orderbook["datetime"].iloc[-1]
    trades = _load_daily_file(root / "trades" / f"{day}.parquet", TRADE_COLUMNS, "trades", day)
    fundings = _load_daily_file(root / "fundings" / f"{day}.parquet", FUNDING_COLUMNS, "fundings", day)
    trades = trades[(trades["datetime"] >= start) & (trades["datetime"] <= end)].reset_index(drop=True)
    fundings = fundings[fundings["datetime"] <= end].reset_index(drop=True)
    if fundings.empty:
        first_funding = _load_daily_file(root / "fundings" / f"{day}.parquet", FUNDING_COLUMNS, "fundings", day, max_rows=1)
        fundings = first_funding
    return MarketData(orderbook=orderbook, trades=trades, fundings=fundings)


def _sort_market_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if df["datetime"].is_monotonic_increasing:
        if isinstance(df.index, pd.RangeIndex) and df.index.start == 0 and df.index.step == 1:
            return df
        df.index = pd.RangeIndex(len(df))
        return df
    source_codes = pd.factorize(df["_source_day"], sort=True)[0] if "_source_day" in df.columns else np.zeros(len(df), dtype=int)
    order = np.lexsort(
        (
            df["_row_id"].to_numpy() if "_row_id" in df.columns else np.arange(len(df)),
            source_codes,
            df["datetime"].astype("int64").to_numpy(),
        )
    )
    return df.take(order).reset_index(drop=True)
