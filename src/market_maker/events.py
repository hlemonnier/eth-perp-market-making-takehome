from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator

import pandas as pd


class EventType(str, Enum):
    BOOK = "book"
    TRADE = "trade"
    FUNDING = "funding"


@dataclass(frozen=True)
class MarketEvent:
    timestamp: pd.Timestamp
    event_type: EventType
    index: int


def merge_event_streams(
    book_times: Iterable[pd.Timestamp],
    trade_times: Iterable[pd.Timestamp],
    funding_times: Iterable[pd.Timestamp],
) -> Iterator[MarketEvent]:
    events: list[MarketEvent] = []
    events.extend(MarketEvent(pd.Timestamp(timestamp), EventType.BOOK, index) for index, timestamp in enumerate(book_times))
    events.extend(MarketEvent(pd.Timestamp(timestamp), EventType.TRADE, index) for index, timestamp in enumerate(trade_times))
    events.extend(MarketEvent(pd.Timestamp(timestamp), EventType.FUNDING, index) for index, timestamp in enumerate(funding_times))
    yield from sorted(events, key=lambda event: (event.timestamp.value, event.event_type.value, event.index))
