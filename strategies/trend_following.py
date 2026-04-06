"""
strategies/trend_following.py
EMA crossover + ADX filter + volume confirmation.
Best in: bull/bear trending markets.
"""

import numpy as np
from strategies.base_strategy import BaseStrategy, Signal


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"

    def __init__(
        self,
        fast_ema: int = 9,
        slow_ema: int = 21,
        signal_ema: int = 50,
        adx_threshold: float = 20.0,
        volume_mult: float = 1.2,
    ):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.signal_ema = signal_ema
        self.adx_threshold = adx_threshold
        self.volume_mult = volume_mult

    def generate_signal(self, ohlcv: list) -> Signal:
        df = self.ohlcv_to_df(ohlcv)
        close = df["close"]
        volume = df["volume"]

        ema_fast = close.ewm(span=self.fast_ema, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_ema, adjust=False).mean()
        ema_signal = close.ewm(span=self.signal_ema, adjust=False).mean()

        # Crossover detection
        cross_up = ema_fast.iloc[-1] > ema_slow.iloc[-1] and ema_fast.iloc[-2] <= ema_slow.iloc[-2]
        cross_down = ema_fast.iloc[-1] < ema_slow.iloc[-1] and ema_fast.iloc[-2] >= ema_slow.iloc[-2]

        # Trend filter: price above/below long EMA
        above_signal = close.iloc[-1] > ema_signal.iloc[-1]

        # Volume confirmation
        avg_vol = volume.iloc[-20:].mean()
        vol_ok = volume.iloc[-1] > avg_vol * self.volume_mult

        if cross_up and above_signal and vol_ok:
            confidence = self._confidence(ema_fast.iloc[-1], ema_slow.iloc[-1], close.iloc[-1])
            return Signal("buy", confidence, "EMA bullish crossover with volume confirmation")

        if cross_down and not above_signal and vol_ok:
            confidence = self._confidence(ema_slow.iloc[-1], ema_fast.iloc[-1], close.iloc[-1])
            return Signal("sell", confidence, "EMA bearish crossover with volume confirmation")

        return Signal("hold", 0.0, "No clear trend signal")

    def _confidence(self, ema_a, ema_b, price) -> float:
        spread = abs(ema_a - ema_b) / price
        return float(min(0.5 + spread * 20, 0.95))
