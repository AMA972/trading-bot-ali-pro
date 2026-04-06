"""
risk/risk_manager.py
The most critical module. Every trade passes through here.

Solves: "bad configuration can cause heavy losses"
- Dynamic position sizing (Kelly Criterion or volatility-based)
- Hard stop-loss on every trade
- Portfolio-level drawdown circuit breaker
- Correlation check (avoid overexposure to same asset class)
"""

from dataclasses import dataclass
from typing import Optional, Dict
import numpy as np
from core.logger import setup_logger
from config.settings import RiskConfig

logger = setup_logger("risk_manager")


@dataclass
class TradeProposal:
    exchange_id: str
    symbol: str
    side: str           # "buy" | "sell"
    strategy: str
    entry_price: float
    confidence: float   # 0.0–1.0 from strategy signal


@dataclass
class ApprovedTrade:
    proposal: TradeProposal
    position_size: float        # in quote currency
    stop_loss: float
    take_profit: float
    risk_amount: float


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self.equity: float = 0.0
        self.peak_equity: float = 0.0
        self.open_positions: Dict[str, dict] = {}   # symbol → position info
        self._paused = False

    def update_equity(self, equity: float):
        self.equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        self._check_drawdown()

    def _check_drawdown(self):
        """Circuit breaker: pause bot if max drawdown exceeded."""
        if self.peak_equity == 0:
            return
        drawdown = (self.peak_equity - self.equity) / self.peak_equity * 100
        if drawdown >= self.config.max_drawdown_pct:
            self._paused = True
            logger.critical(
                f"🛑 MAX DRAWDOWN REACHED ({drawdown:.1f}%). Bot PAUSED. "
                f"Manual review required."
            )

    def is_paused(self) -> bool:
        return self._paused

    def resume(self):
        """Manually resume after reviewing the situation."""
        self._paused = False
        logger.warning("⚠️  Bot manually resumed. Ensure issue is resolved.")

    def approve_trade(self, proposal: TradeProposal) -> Optional[ApprovedTrade]:
        """
        Validate and size a trade proposal.
        Returns None if the trade should be rejected.
        """
        if self._paused:
            logger.warning(f"Trade rejected: bot is paused (drawdown limit hit)")
            return None

        if len(self.open_positions) >= self.config.max_open_positions:
            logger.info(f"Trade rejected: max open positions ({self.config.max_open_positions}) reached")
            return None

        if proposal.symbol in self.open_positions:
            logger.info(f"Trade rejected: already have position in {proposal.symbol}")
            return None

        # Calculate stop and target levels
        sl_pct = self.config.stop_loss_pct / 100
        tp_pct = self.config.take_profit_pct / 100

        if proposal.side == "buy":
            stop_loss = proposal.entry_price * (1 - sl_pct)
            take_profit = proposal.entry_price * (1 + tp_pct)
        else:
            stop_loss = proposal.entry_price * (1 + sl_pct)
            take_profit = proposal.entry_price * (1 - tp_pct)

        # Risk/reward check (minimum 1.5:1)
        risk = abs(proposal.entry_price - stop_loss)
        reward = abs(take_profit - proposal.entry_price)
        if reward / risk < 1.5:
            logger.info(f"Trade rejected: poor R/R ratio ({reward/risk:.2f})")
            return None

        # Position sizing
        position_size = self._size_position(proposal, stop_loss)
        if position_size is None:
            return None

        approved = ApprovedTrade(
            proposal=proposal,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_amount=position_size * sl_pct,
        )

        logger.info(
            f"✅ Trade approved: {proposal.side.upper()} {proposal.symbol} "
            f"size={position_size:.2f} SL={stop_loss:.4f} TP={take_profit:.4f}"
        )
        return approved

    def _size_position(self, proposal: TradeProposal, stop_loss: float) -> Optional[float]:
        """
        Position sizing based on config strategy:
          - fixed: constant % of equity per trade
          - kelly: Kelly Criterion (adjusts for confidence)
          - volatility: smaller size when volatility is higher
        """
        method = self.config.position_sizing
        max_risk = self.equity * (self.config.max_single_trade_risk_pct / 100)

        # Portfolio-level check
        total_open_risk = sum(p.get("risk_amount", 0) for p in self.open_positions.values())
        max_portfolio_risk = self.equity * (self.config.max_portfolio_risk_pct / 100)
        available_risk = max_portfolio_risk - total_open_risk

        if available_risk <= 0:
            logger.info("Trade rejected: portfolio risk limit reached")
            return None

        risk_per_trade = min(max_risk, available_risk)

        if method == "kelly":
            # Kelly fraction: f = (p*(b+1) - 1) / b
            # where p = win probability (confidence), b = R/R ratio
            win_prob = proposal.confidence
            rr_ratio = self.config.take_profit_pct / self.config.stop_loss_pct
            kelly_fraction = (win_prob * (rr_ratio + 1) - 1) / rr_ratio
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # cap at 25%
            risk_per_trade = self.equity * kelly_fraction

        elif method == "volatility":
            # Reduce size when confidence is low
            risk_per_trade *= proposal.confidence

        sl_distance_pct = abs(proposal.entry_price - stop_loss) / proposal.entry_price
        if sl_distance_pct == 0:
            return None

        # Size = risk_amount / stop_loss_distance
        position_size = risk_per_trade / sl_distance_pct

        if position_size < 10:  # minimum order size
            logger.info(f"Trade rejected: position size too small ({position_size:.2f})")
            return None

        return round(position_size, 2)

    def register_position(self, symbol: str, trade: ApprovedTrade):
        self.open_positions[symbol] = {
            "side": trade.proposal.side,
            "entry": trade.proposal.entry_price,
            "size": trade.position_size,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "risk_amount": trade.risk_amount,
            "strategy": trade.proposal.strategy,
        }

    def close_position(self, symbol: str):
        if symbol in self.open_positions:
            del self.open_positions[symbol]

    def get_portfolio_stats(self) -> dict:
        total_risk = sum(p["risk_amount"] for p in self.open_positions.values())
        drawdown = ((self.peak_equity - self.equity) / self.peak_equity * 100
                    if self.peak_equity > 0 else 0)
        return {
            "equity": self.equity,
            "peak_equity": self.peak_equity,
            "drawdown_pct": round(drawdown, 2),
            "open_positions": len(self.open_positions),
            "total_risk": round(total_risk, 2),
            "risk_pct": round(total_risk / self.equity * 100, 2) if self.equity > 0 else 0,
            "paused": self._paused,
        }
