"""
strategies/momentum.py
MACD histogram + volume surge detection.
Best in: high-volatility markets and breakouts.
"""

import numpy as np
from strategies.base_strategy import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        vol_surge_mult: float = 2.0,
        lookback: int = 3,
    ):
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.vol_surge_mult = vol_surge_mult
        self.lookback = lookback

    def generate_signal(self, ohlcv: list) -> Signal:
        df = self.ohlcv_to_df(ohlcv)
        close = df["close"]
        volume = df["volume"]

        # MACD
        ema_fast = close.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd_line - signal_line

        # Volume surge
        avg_vol = volume.iloc[-20:-1].mean()
        vol_surge = volume.iloc[-1] > avg_vol * self.vol_surge_mult

        # Histogram momentum: increasing for N candles
        hist_rising = all(
            histogram.iloc[-i] > histogram.iloc[-i - 1]
            for i in range(1, self.lookback + 1)
        )
        hist_falling = all(
            histogram.iloc[-i] < histogram.iloc[-i - 1]
            for i in range(1, self.lookback + 1)
        )

        macd_positive = macd_line.iloc[-1] > 0
        macd_negative = macd_line.iloc[-1] < 0

        # Bullish momentum: MACD positive, histogram rising, volume surge
        if macd_positive and hist_rising and vol_surge:
            conf = self._confidence(histogram, volume, avg_vol)
            return Signal("buy", conf, f"Bullish momentum with volume surge ({volume.iloc[-1]/avg_vol:.1f}x avg)")

        # Bearish momentum
        if macd_negative and hist_falling and vol_surge:
            conf = self._confidence(histogram, volume, avg_vol)
            return Signal("sell", conf, f"Bearish momentum with volume surge ({volume.iloc[-1]/avg_vol:.1f}x avg)")

        return Signal("hold", 0.0, "No momentum signal")

    def _confidence(self, histogram, volume, avg_vol) -> float:
        hist_strength = abs(histogram.iloc[-1]) / (abs(histogram.iloc[-20:]).mean() + 1e-9)
        vol_strength = float(volume.iloc[-1]) / (avg_vol + 1e-9)
        score = min((hist_strength + vol_strength / 4) / 2, 1.0)
        return float(max(0.5, min(score, 0.95)))
