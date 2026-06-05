from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterator

import pandas as pd

from market_maker.data_loader import MarketData


class EventType(IntEnum):
    TRADE = 0
    ORDERBOOK = 1
    FUNDING = 2


@dataclass(frozen=True)
class EventGroup:
    timestamp: pd.Timestamp
    trades: list[int]
    orderbooks: list[int]
    fundings: list[int]


def build_event_index(data: MarketData) -> pd.DataFrame:
    frames = [
        pd.DataFrame({"datetime": data.trades["datetime"], "event_type": EventType.TRADE, "index": data.trades.index}),
        pd.DataFrame({"datetime": data.orderbook["datetime"], "event_type": EventType.ORDERBOOK, "index": data.orderbook.index}),
        pd.DataFrame({"datetime": data.fundings["datetime"], "event_type": EventType.FUNDING, "index": data.fundings.index}),
    ]
    events = pd.concat(frames, ignore_index=True)
    return events.sort_values(["datetime", "event_type", "index"], kind="mergesort").reset_index(drop=True)


def iter_event_groups(data: MarketData) -> Iterator[EventGroup]:
    events = build_event_index(data)
    for timestamp, group in events.groupby("datetime", sort=False):
        trades = group.loc[group["event_type"] == EventType.TRADE, "index"].astype(int).tolist()
        orderbooks = group.loc[group["event_type"] == EventType.ORDERBOOK, "index"].astype(int).tolist()
        fundings = group.loc[group["event_type"] == EventType.FUNDING, "index"].astype(int).tolist()
        yield EventGroup(timestamp=pd.Timestamp(timestamp), trades=trades, orderbooks=orderbooks, fundings=fundings)
