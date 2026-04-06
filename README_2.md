# TradingBot Pro

Bot de trading algorithmique autonome multi-exchange et multi-stratégie, développé en Python.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)
![Exchange](https://img.shields.io/badge/Exchange-Binance%20%7C%20Kraken%20%7C%20100%2B-orange?style=flat-square)

## Fonctionnalités

- **Multi-exchange** — compatible avec 100+ exchanges via `ccxt` (Binance, Kraken, Coinbase...)
- **3 stratégies** — Trend Following (EMA), Mean Reversion (Bollinger+RSI), Momentum (MACD)
- **Détection de régime** — sélection automatique de la meilleure stratégie selon le marché
- **Risk management dynamique** — Kelly Criterion, stop-loss automatique, circuit-breaker sur drawdown
- **Mode dry run** — simulation complète sans argent réel
- **Alertes** — webhook Slack/Discord/Telegram en temps réel

## Architecture

```
trading_bot/
├── main.py                    # Point d'entrée
├── config/
│   └── settings.py            # Configuration YAML
├── core/
│   ├── bot_engine.py          # Orchestrateur principal
│   ├── exchange_manager.py    # Connexion exchanges (ccxt)
│   └── regime_detector.py    # Détection du régime de marché
├── strategies/
│   ├── trend_following.py     # EMA crossover + ADX
│   ├── mean_reversion.py      # Bollinger Bands + RSI
│   └── momentum.py            # MACD + volume surge
├── risk/
│   └── risk_manager.py        # Gestion du risque
└── monitoring/
    └── monitor.py             # Alertes et métriques
```

## Problèmes classiques résolus

| Problème | Solution |
|---|---|
| Mauvais paramétrage → pertes | Stop-loss automatique + circuit-breaker drawdown max |
| Stratégie obsolète | Détection automatique du régime de marché |
| Surveillance manuelle | Alertes webhook + logs rotatifs automatiques |
| APIs qui changent | `ccxt` unifie 100+ exchanges, 1 ligne pour changer |

## Installation

```bash
git clone https://github.com/AMA972/trading-bot-ali-pro.git
cd trading-bot-ali-pro
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
```

## Configuration

```yaml
# config/config.yaml
dry_run: true  # Toujours commencer en simulation

exchanges:
  - id: binance
    api_key_env: BINANCE_API_KEY
    api_secret_env: BINANCE_API_SECRET
    sandbox: true

symbols:
  - BTC/USDT
  - ETH/USDT
  - SOL/USDT

risk:
  max_drawdown_pct: 10.0
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  position_sizing: kelly
```

## Lancement

```bash
# Simulation (aucun argent réel)
python main.py

# Variables d'environnement
export BINANCE_API_KEY="votre_clé"
export BINANCE_API_SECRET="votre_secret"
```

## Stack technique

- **Python 3.10+** — langage principal
- **ccxt** — abstraction multi-exchange
- **pandas / numpy** — calcul des indicateurs techniques
- **aiohttp** — requêtes asynchrones
- **asyncio** — architecture non-bloquante
- **PyYAML** — configuration

## Avertissement

Le trading comporte des risques de perte en capital. Ce bot est un outil éducatif et expérimental. Ne tradez jamais plus que ce que vous pouvez vous permettre de perdre. Commencez toujours en mode `dry_run: true`.

## Auteur

**Ali ADOUM MAHAMAT** — [GitHub](https://github.com/AMA972)
