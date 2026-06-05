from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def _load_daily_file(path: Path, required: list[str], label: str, day: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    validate_columns(df, required, str(path))
    df = df.copy()
    df["datetime"] = normalize_datetime(df["datetime"])
    df["_source_day"] = day
    df["_row_id"] = range(len(df))
    return df.sort_values(["datetime", "_row_id"], kind="mergesort").reset_index(drop=True)


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
        orderbook=pd.concat(orderbooks, ignore_index=True).sort_values(["datetime", "_source_day", "_row_id"], kind="mergesort").reset_index(drop=True),
        trades=pd.concat(trades, ignore_index=True).sort_values(["datetime", "_source_day", "_row_id"], kind="mergesort").reset_index(drop=True),
        fundings=pd.concat(fundings, ignore_index=True).sort_values(["datetime", "_source_day", "_row_id"], kind="mergesort").reset_index(drop=True),
    )
