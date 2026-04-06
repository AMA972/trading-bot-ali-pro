"""strategies/base_strategy.py — Abstract base for all strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    side: str           # "buy" | "sell" | "hold"
    confidence: float   # 0.0 – 1.0
    reason: str         # human-readable explanation


class BaseStrategy(ABC):
    name: str = "base"

    def ohlcv_to_df(self, ohlcv: list) -> pd.DataFrame:
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df.set_index("timestamp")

    @abstractmethod
    def generate_signal(self, ohlcv: list) -> Signal:
        """Analyse OHLCV data and return a trading signal."""
        ...
