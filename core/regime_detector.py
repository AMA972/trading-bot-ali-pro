"""
core/regime_detector.py
Detects the current market regime (Trending / Ranging / Volatile / Bear)
and routes to the most appropriate strategy automatically.

This solves: "strategies that were effective yesterday can fail tomorrow"
"""

import numpy as np
import pandas as pd
from enum import Enum
from core.logger import setup_logger

logger = setup_logger("regime_detector")


class MarketRegime(Enum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


# Strategy best suited to each regime
REGIME_STRATEGY_MAP = {
    MarketRegime.BULL_TREND: "trend_following",
    MarketRegime.BEAR_TREND: "trend_following",   # short-selling version
    MarketRegime.RANGING: "mean_reversion",
    MarketRegime.HIGH_VOLATILITY: "momentum",
    MarketRegime.UNKNOWN: "mean_reversion",       # safest default
}


class RegimeDetector:
    def __init__(self, adx_period: int = 14, atr_period: int = 14):
        self.adx_period = adx_period
        self.atr_period = atr_period

    def detect(self, ohlcv: list) -> MarketRegime:
        """
        Detect regime from raw OHLCV data.
        Uses ADX (trend strength), ATR (volatility), and price slope.
        """
        if len(ohlcv) < 50:
            return MarketRegime.UNKNOWN

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        adx = self._calc_adx(df)
        atr_pct = self._calc_atr_pct(df)
        trend_slope = self._calc_slope(df["close"].values)

        # High volatility regime
        if atr_pct > 4.0:
            regime = MarketRegime.HIGH_VOLATILITY

        # Strong trend regimes (ADX > 25 = trending market)
        elif adx > 25:
            regime = MarketRegime.BULL_TREND if trend_slope > 0 else MarketRegime.BEAR_TREND

        # Ranging market
        else:
            regime = MarketRegime.RANGING

        logger.debug(
            f"Regime: {regime.value} | ADX={adx:.1f} | ATR%={atr_pct:.2f} | Slope={trend_slope:.4f}"
        )
        return regime

    def best_strategy(self, ohlcv: list) -> str:
        regime = self.detect(ohlcv)
        strategy = REGIME_STRATEGY_MAP[regime]
        logger.info(f"🎯 Market regime: {regime.value} → using strategy: {strategy}")
        return strategy

    def _calc_adx(self, df: pd.DataFrame) -> float:
        """Average Directional Index — measures trend strength (not direction)."""
        n = self.adx_period
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        tr = np.maximum(high[1:] - low[1:],
               np.maximum(abs(high[1:] - close[:-1]),
                          abs(low[1:] - close[:-1])))

        dm_plus = np.where((high[1:] - high[:-1]) > (low[:-1] - low[1:]),
                           np.maximum(high[1:] - high[:-1], 0), 0)
        dm_minus = np.where((low[:-1] - low[1:]) > (high[1:] - high[:-1]),
                            np.maximum(low[:-1] - low[1:], 0), 0)

        def smooth(arr, period):
            result = np.zeros(len(arr))
            result[period - 1] = arr[:period].sum()
            for i in range(period, len(arr)):
                result[i] = result[i - 1] - result[i - 1] / period + arr[i]
            return result

        tr_s = smooth(tr, n)
        dm_plus_s = smooth(dm_plus, n)
        dm_minus_s = smooth(dm_minus, n)

        with np.errstate(divide="ignore", invalid="ignore"):
            di_plus = np.where(tr_s != 0, 100 * dm_plus_s / tr_s, 0)
            di_minus = np.where(tr_s != 0, 100 * dm_minus_s / tr_s, 0)
            dx = np.where((di_plus + di_minus) != 0,
                          100 * abs(di_plus - di_minus) / (di_plus + di_minus), 0)

        adx = dx[-n:].mean() if len(dx) >= n else 0
        return float(adx)

    def _calc_atr_pct(self, df: pd.DataFrame) -> float:
        """ATR as % of price — measures relative volatility."""
        n = self.atr_period
        high = df["high"].values[-n - 1:]
        low = df["low"].values[-n - 1:]
        close = df["close"].values[-n - 1:]

        tr = np.maximum(high[1:] - low[1:],
               np.maximum(abs(high[1:] - close[:-1]),
                          abs(low[1:] - close[:-1])))
        atr = tr.mean()
        return float(atr / close[-1] * 100)

    def _calc_slope(self, prices: np.ndarray, period: int = 20) -> float:
        """Linear regression slope of recent prices."""
        y = prices[-period:]
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]
        return float(slope / y[0])  # normalized
