"""
strategies/mean_reversion.py
Bollinger Bands + RSI divergence.
Best in: sideways / ranging markets.
"""

import numpy as np
from strategies.base_strategy import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def generate_signal(self, ohlcv: list) -> Signal:
        df = self.ohlcv_to_df(ohlcv)
        close = df["close"]

        # Bollinger Bands
        sma = close.rolling(self.bb_period).mean()
        std = close.rolling(self.bb_period).std()
        upper = sma + self.bb_std * std
        lower = sma - self.bb_std * std

        price = close.iloc[-1]
        bb_upper = upper.iloc[-1]
        bb_lower = lower.iloc[-1]
        bb_mid = sma.iloc[-1]

        # RSI
        rsi = self._calc_rsi(close)

        # Buy: price touches/breaks lower BB + RSI oversold
        if price <= bb_lower and rsi <= self.rsi_oversold:
            conf = self._buy_confidence(price, bb_lower, bb_mid, rsi)
            return Signal("buy", conf, f"Price at lower BB ({price:.4f} ≤ {bb_lower:.4f}), RSI={rsi:.1f}")

        # Sell: price touches/breaks upper BB + RSI overbought
        if price >= bb_upper and rsi >= self.rsi_overbought:
            conf = self._sell_confidence(price, bb_upper, bb_mid, rsi)
            return Signal("sell", conf, f"Price at upper BB ({price:.4f} ≥ {bb_upper:.4f}), RSI={rsi:.1f}")

        return Signal("hold", 0.0, f"Price within bands, RSI={rsi:.1f}")

    def _calc_rsi(self, close, period: int = None) -> float:
        period = period or self.rsi_period
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _buy_confidence(self, price, lower, mid, rsi) -> float:
        # Deeper below band + lower RSI = higher confidence
        band_penetration = (lower - price) / (mid - lower + 1e-9)
        rsi_score = (self.rsi_oversold - rsi) / self.rsi_oversold
        return float(min(0.5 + (band_penetration + rsi_score) * 0.25, 0.95))

    def _sell_confidence(self, price, upper, mid, rsi) -> float:
        band_penetration = (price - upper) / (upper - mid + 1e-9)
        rsi_score = (rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
        return float(min(0.5 + (band_penetration + rsi_score) * 0.25, 0.95))
