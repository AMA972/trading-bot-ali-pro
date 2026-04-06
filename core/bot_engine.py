"""
core/bot_engine.py
Main orchestrator. Connects all modules and runs the trading loop.
"""

import asyncio
from datetime import datetime
from typing import Dict, List
from config.settings import BotConfig
from core.exchange_manager import ExchangeManager
from core.regime_detector import RegimeDetector
from core.logger import setup_logger
from risk.risk_manager import RiskManager, TradeProposal
from strategies.registry import get_strategy
from monitoring.monitor import Monitor, TradeRecord

logger = setup_logger("bot_engine")


class BotEngine:
    def __init__(self, config: BotConfig):
        self.config = config
        self.exchange_manager = ExchangeManager(config.exchanges)
        self.risk_manager = RiskManager(config.risk)
        self.regime_detector = RegimeDetector()
        self.monitor = Monitor(config.monitoring)
        self._running = False

        # Build strategy pool
        self.strategies = {
            name: get_strategy(name)
            for name in config.strategy.active_strategies
        }

        # Track active orders: symbol → order info
        self.active_orders: Dict[str, dict] = {}

    async def run(self):
        self._running = True
        await self.exchange_manager.connect_all()
        await self.monitor.start()

        if not self.exchange_manager.exchanges:
            logger.error("No exchanges connected. Exiting.")
            return

        logger.info(
            f"Bot running | DRY RUN: {self.config.dry_run} | "
            f"Symbols: {self.config.symbols} | "
            f"Strategies: {list(self.strategies.keys())}"
        )

        await asyncio.gather(
            self._trading_loop(),
            self._position_monitor_loop(),
        )

    async def _trading_loop(self):
        """Main loop: fetch data → detect regime → generate signal → manage risk → execute."""
        while self._running:
            if self.risk_manager.is_paused():
                await self.monitor.alert(
                    "CRITICAL",
                    "Bot is PAUSED due to max drawdown. Manual review required."
                )
                await asyncio.sleep(300)  # wait 5 min before re-alerting
                continue

            for exchange_id in self.exchange_manager.exchanges:
                for symbol in self.config.symbols:
                    try:
                        await self._process_symbol(exchange_id, symbol)
                    except Exception as e:
                        logger.error(f"Error processing {symbol} on {exchange_id}: {e}")

            await asyncio.sleep(60)  # run cycle every 60 seconds

    async def _process_symbol(self, exchange_id: str, symbol: str):
        # Skip if already in a position
        if symbol in self.risk_manager.open_positions:
            return

        # Fetch OHLCV for primary timeframe
        primary_tf = self.config.timeframes[0]
        ohlcv = await self.exchange_manager.fetch_ohlcv(exchange_id, symbol, primary_tf, limit=200)
        if not ohlcv or len(ohlcv) < 50:
            return

        # Detect market regime → select best strategy
        if self.config.strategy.regime_detection:
            strategy_name = self.regime_detector.best_strategy(ohlcv)
        else:
            strategy_name = self.config.strategy.active_strategies[0]

        strategy = self.strategies.get(strategy_name)
        if not strategy:
            return

        # Generate signal
        signal = strategy.generate_signal(ohlcv)
        if signal.side == "hold" or signal.confidence < 0.55:
            return

        # Get current price
        ticker = await self.exchange_manager.fetch_ticker(exchange_id, symbol)
        entry_price = ticker["last"]

        # Update equity
        balance = await self.exchange_manager.fetch_balance(exchange_id)
        equity = float(balance.get("USDT", {}).get("total", 0) or
                       balance.get("USD", {}).get("total", 0) or 0)
        if equity > 0:
            self.risk_manager.update_equity(equity)

        # Risk approval
        proposal = TradeProposal(
            exchange_id=exchange_id,
            symbol=symbol,
            side=signal.side,
            strategy=strategy_name,
            entry_price=entry_price,
            confidence=signal.confidence,
        )
        approved = self.risk_manager.approve_trade(proposal)
        if not approved:
            return

        # Execute
        await self._execute_trade(approved)

    async def _execute_trade(self, trade):
        p = trade.proposal
        amount = trade.position_size / p.entry_price

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] Would {p.side.upper()} {amount:.6f} {p.symbol} "
                f"@ {p.entry_price:.4f} | SL={trade.stop_loss:.4f} | TP={trade.take_profit:.4f} "
                f"| Strategy={p.strategy} | Confidence={p.confidence:.0%}"
            )
            self.risk_manager.register_position(p.symbol, trade)
            self.active_orders[p.symbol] = {
                "trade": trade,
                "entry_time": datetime.utcnow(),
                "dry_run": True,
            }
            return

        try:
            # Place market order
            order = await self.exchange_manager.create_order(
                p.exchange_id, p.symbol, "market", p.side, amount
            )

            # Place stop-loss order
            sl_side = "sell" if p.side == "buy" else "buy"
            await self.exchange_manager.create_order(
                p.exchange_id, p.symbol, "stop_market", sl_side, amount,
                params={"stopPrice": trade.stop_loss, "reduceOnly": True},
            )

            # Place take-profit order
            await self.exchange_manager.create_order(
                p.exchange_id, p.symbol, "take_profit_market", sl_side, amount,
                params={"stopPrice": trade.take_profit, "reduceOnly": True},
            )

            self.risk_manager.register_position(p.symbol, trade)
            self.active_orders[p.symbol] = {
                "trade": trade,
                "order": order,
                "entry_time": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            await self.monitor.alert("WARNING", f"Order failed: {p.symbol} — {e}")

    async def _position_monitor_loop(self):
        """Check open positions and handle exits."""
        while self._running:
            await asyncio.sleep(30)
            for symbol, info in list(self.active_orders.items()):
                try:
                    await self._check_position(symbol, info)
                except Exception as e:
                    logger.error(f"Position check failed for {symbol}: {e}")

    async def _check_position(self, symbol: str, info: dict):
        trade = info["trade"]
        p = trade.proposal
        exchange_id = p.exchange_id

        if info.get("dry_run"):
            # Simulate exit for dry run (check if SL/TP hit)
            ticker = await self.exchange_manager.fetch_ticker(exchange_id, symbol)
            price = ticker["last"]

            hit_tp = (p.side == "buy" and price >= trade.take_profit) or \
                     (p.side == "sell" and price <= trade.take_profit)
            hit_sl = (p.side == "buy" and price <= trade.stop_loss) or \
                     (p.side == "sell" and price >= trade.stop_loss)

            if hit_tp or hit_sl:
                exit_price = trade.take_profit if hit_tp else trade.stop_loss
                pnl = (exit_price - p.entry_price) * (trade.position_size / p.entry_price)
                if p.side == "sell":
                    pnl = -pnl

                self.monitor.record_trade(TradeRecord(
                    symbol=symbol, side=p.side, entry=p.entry_price,
                    exit_price=exit_price, pnl=pnl, strategy=p.strategy,
                ))
                self.risk_manager.close_position(symbol)
                del self.active_orders[symbol]

                reason = "TP" if hit_tp else "SL"
                logger.info(f"[DRY RUN] Position closed: {symbol} via {reason} | PnL={pnl:+.2f}")

    async def shutdown(self):
        logger.info("Shutting down bot gracefully...")
        self._running = False
        await self.exchange_manager.close_all()
        await self.monitor.stop()
        logger.info("Bot shut down cleanly. Goodbye.")
