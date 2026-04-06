"""
core/exchange_manager.py
Abstracts ALL exchange interactions through ccxt.
Adding a new exchange = one line in config.yaml. No code change needed.
"""

import asyncio
import ccxt.async_support as ccxt
from typing import Dict, List, Optional
from core.logger import setup_logger
from config.settings import ExchangeConfig

logger = setup_logger("exchange_manager")


class ExchangeManager:
    def __init__(self, exchange_configs: List[ExchangeConfig]):
        self.configs = exchange_configs
        self.exchanges: Dict[str, ccxt.Exchange] = {}

    async def connect_all(self):
        """Initialize and test all configured exchanges."""
        for cfg in self.configs:
            try:
                exchange_class = getattr(ccxt, cfg.id)
                exchange = exchange_class({
                    "apiKey": cfg.api_key,
                    "secret": cfg.api_secret,
                    "enableRateLimit": cfg.rate_limit,
                    "options": cfg.options,
                })
                if cfg.sandbox:
                    exchange.set_sandbox_mode(True)

                await exchange.load_markets()
                self.exchanges[cfg.id] = exchange
                logger.info(f"✅ Connected to {cfg.id} ({'SANDBOX' if cfg.sandbox else 'LIVE'})")
            except Exception as e:
                logger.error(f"❌ Failed to connect to {cfg.id}: {e}")

    async def fetch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 500):
        """Fetch candlestick data with automatic retry."""
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            raise ValueError(f"Exchange {exchange_id} not connected")

        for attempt in range(3):
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return ohlcv
            except ccxt.RateLimitExceeded:
                wait = 2 ** attempt
                logger.warning(f"Rate limit hit on {exchange_id}, retrying in {wait}s...")
                await asyncio.sleep(wait)
            except ccxt.NetworkError as e:
                logger.warning(f"Network error on {exchange_id}: {e}, retrying...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"fetch_ohlcv failed: {e}")
                raise

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> dict:
        exchange = self.exchanges[exchange_id]
        return await exchange.fetch_ticker(symbol)

    async def fetch_balance(self, exchange_id: str) -> dict:
        exchange = self.exchanges[exchange_id]
        return await exchange.fetch_balance()

    async def create_order(
        self,
        exchange_id: str,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: dict = None,
    ) -> dict:
        exchange = self.exchanges[exchange_id]
        params = params or {}
        try:
            order = await exchange.create_order(symbol, order_type, side, amount, price, params)
            logger.info(f"📋 Order placed [{exchange_id}] {side.upper()} {amount} {symbol} @ {price or 'market'}")
            return order
        except ccxt.InsufficientFunds as e:
            logger.error(f"Insufficient funds: {e}")
            raise
        except Exception as e:
            logger.error(f"Order failed: {e}")
            raise

    async def cancel_order(self, exchange_id: str, order_id: str, symbol: str):
        exchange = self.exchanges[exchange_id]
        return await exchange.cancel_order(order_id, symbol)

    async def fetch_open_orders(self, exchange_id: str, symbol: str = None):
        exchange = self.exchanges[exchange_id]
        return await exchange.fetch_open_orders(symbol)

    async def close_all(self):
        for exchange in self.exchanges.values():
            await exchange.close()
        logger.info("All exchange connections closed.")
