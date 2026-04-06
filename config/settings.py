"""
config/settings.py — Central configuration loader with validation.

HOW TO USE:
  1. Copy config.example.yaml → config.yaml
  2. Fill in your exchange credentials
  3. Tune risk/strategy parameters to your taste
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ExchangeConfig:
    id: str                     # ccxt exchange id (e.g. 'binance', 'kraken')
    api_key: str
    api_secret: str
    sandbox: bool = True        # ALWAYS start in sandbox mode !
    rate_limit: bool = True
    options: Dict = field(default_factory=dict)


@dataclass
class RiskConfig:
    max_portfolio_risk_pct: float = 1.0     # max % of capital at risk at once
    max_single_trade_risk_pct: float = 0.5  # max % per trade
    max_drawdown_pct: float = 10.0          # hard stop: pause bot if exceeded
    stop_loss_pct: float = 2.0              # default stop-loss per trade
    take_profit_pct: float = 4.0            # default take-profit per trade
    max_open_positions: int = 5
    position_sizing: str = "kelly"          # "fixed" | "kelly" | "volatility"


@dataclass
class StrategyConfig:
    active_strategies: List[str] = field(
        default_factory=lambda: ["trend_following", "mean_reversion", "momentum"]
    )
    regime_detection: bool = True           # auto-select strategy per market regime
    rebalance_interval: int = 3600          # seconds between strategy rebalances
    backtest_on_start: bool = True          # quick backtest before going live


@dataclass
class MonitoringConfig:
    dashboard_port: int = 8080
    alert_email: Optional[str] = None
    alert_webhook: Optional[str] = None     # Slack / Discord / Telegram webhook
    log_level: str = "INFO"
    metrics_interval: int = 60             # seconds


@dataclass
class BotConfig:
    exchanges: List[ExchangeConfig]
    symbols: List[str]                      # e.g. ["BTC/USDT", "ETH/USDT"]
    timeframes: List[str]                   # e.g. ["1h", "4h", "1d"]
    risk: RiskConfig
    strategy: StrategyConfig
    monitoring: MonitoringConfig
    dry_run: bool = True                    # True = simulate orders, no real money


def load_config(path: str = "config/config.yaml") -> BotConfig:
    config_path = Path(path)

    if not config_path.exists():
        # Generate example config on first run
        _write_example_config()
        raise FileNotFoundError(
            f"No config found at {path}. "
            f"An example has been created at config/config.example.yaml — "
            f"copy it, fill in your credentials, and restart."
        )

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    exchanges = [
        ExchangeConfig(
            id=ex["id"],
            api_key=os.environ.get(ex.get("api_key_env", ""), ex.get("api_key", "")),
            api_secret=os.environ.get(ex.get("api_secret_env", ""), ex.get("api_secret", "")),
            sandbox=ex.get("sandbox", True),
            options=ex.get("options", {}),
        )
        for ex in raw.get("exchanges", [])
    ]

    return BotConfig(
        exchanges=exchanges,
        symbols=raw.get("symbols", ["BTC/USDT", "ETH/USDT"]),
        timeframes=raw.get("timeframes", ["1h", "4h"]),
        risk=RiskConfig(**raw.get("risk", {})),
        strategy=StrategyConfig(**raw.get("strategy", {})),
        monitoring=MonitoringConfig(**raw.get("monitoring", {})),
        dry_run=raw.get("dry_run", True),
    )


def _write_example_config():
    example = """# TradingBot Pro — Example Configuration
# Copy this file to config.yaml and fill in your details.

dry_run: true   # Set to false only when you're confident in your strategy

exchanges:
  - id: binance
    api_key_env: BINANCE_API_KEY       # reads from environment variable
    api_secret_env: BINANCE_API_SECRET
    sandbox: true
  # - id: kraken
  #   api_key_env: KRAKEN_API_KEY
  #   api_secret_env: KRAKEN_API_SECRET

symbols:
  - BTC/USDT
  - ETH/USDT
  - SOL/USDT

timeframes:
  - 1h
  - 4h

risk:
  max_portfolio_risk_pct: 1.0
  max_single_trade_risk_pct: 0.5
  max_drawdown_pct: 10.0
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_open_positions: 5
  position_sizing: kelly   # fixed | kelly | volatility

strategy:
  active_strategies:
    - trend_following
    - mean_reversion
    - momentum
  regime_detection: true
  rebalance_interval: 3600
  backtest_on_start: true

monitoring:
  dashboard_port: 8080
  alert_webhook: ""        # Slack/Discord/Telegram webhook URL
  log_level: INFO
  metrics_interval: 60
"""
    Path("config").mkdir(exist_ok=True)
    with open("config/config.example.yaml", "w") as f:
        f.write(example)
