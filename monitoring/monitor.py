"""
monitoring/monitor.py
Real-time monitoring, alerting, and performance tracking.

Solves: "requires regular monitoring"
→ The bot monitors itself and sends alerts when action is needed.
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from collections import deque
from typing import Optional, List, Dict
from core.logger import setup_logger
from config.settings import MonitoringConfig

logger = setup_logger("monitor")


class TradeRecord:
    def __init__(self, symbol, side, entry, exit_price, pnl, strategy):
        self.symbol = symbol
        self.side = side
        self.entry = entry
        self.exit_price = exit_price
        self.pnl = pnl
        self.strategy = strategy
        self.timestamp = datetime.utcnow().isoformat()


class Monitor:
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.trade_history: deque = deque(maxlen=1000)
        self.alerts: deque = deque(maxlen=100)
        self.metrics: Dict = {}
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._metrics_loop())
        logger.info(f"📊 Monitoring started | Dashboard: http://localhost:{self.config.dashboard_port}")

    async def stop(self):
        self._running = False

    def record_trade(self, record: TradeRecord):
        self.trade_history.append(record)
        emoji = "🟢" if record.pnl >= 0 else "🔴"
        logger.info(
            f"{emoji} Trade closed: {record.symbol} {record.side.upper()} "
            f"PnL={record.pnl:+.2f} | Strategy={record.strategy}"
        )

    async def alert(self, level: str, message: str):
        """Send an alert (log + optional webhook)."""
        entry = {"time": datetime.utcnow().isoformat(), "level": level, "message": message}
        self.alerts.append(entry)

        if level == "CRITICAL":
            logger.critical(f"🚨 ALERT: {message}")
        elif level == "WARNING":
            logger.warning(f"⚠️  ALERT: {message}")
        else:
            logger.info(f"ℹ️  ALERT: {message}")

        if self.config.alert_webhook:
            await self._send_webhook(level, message)

    async def _send_webhook(self, level: str, message: str):
        """Send to Slack / Discord / Telegram webhook."""
        emoji_map = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}
        payload = {
            "text": f"{emoji_map.get(level, '')} *TradingBot [{level}]*\n{message}"
        }
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.config.alert_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception as e:
            logger.warning(f"Webhook delivery failed: {e}")

    def update_metrics(self, metrics: dict):
        self.metrics.update(metrics)
        self.metrics["updated_at"] = datetime.utcnow().isoformat()

    async def _metrics_loop(self):
        while self._running:
            await asyncio.sleep(self.config.metrics_interval)
            self._log_performance_summary()

    def _log_performance_summary(self):
        if not self.trade_history:
            return
        trades = list(self.trade_history)
        wins = [t for t in trades if t.pnl > 0]
        total_pnl = sum(t.pnl for t in trades)
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        logger.info(
            f"📈 Performance | Trades: {len(trades)} | "
            f"Win rate: {win_rate:.1f}% | "
            f"Total PnL: {total_pnl:+.2f}"
        )

    def get_stats(self) -> dict:
        trades = list(self.trade_history)
        if not trades:
            return {"trades": 0}
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in trades)
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)), 2)
            if losses else float("inf"),
            "recent_alerts": list(self.alerts)[-5:],
        }
