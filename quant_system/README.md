# Quant System

Clean, config-driven, modular Python quantitative trading system (4H, multi-asset futures universe) with:

- Feature engineering (momentum/volatility/trend/volume)
- Global LightGBM regression model
- Weekly rolling retraining (24-month rolling window)
- Long/short signals with dynamic thresholding
- Risk management (ATR stop sizing + portfolio risk cap)
- Mock execution layer (fees + slippage)
- SQLite journal + weekly performance report

## Setup

Create a virtual env and install dependencies.

## Data

Place one CSV per asset in `quant_system/data/csv/` named like:

- `BTC_USDT.csv`
- `ETH_USDT.csv`

CSV columns (case-insensitive): `timestamp, open, high, low, close, volume`.
Timestamps should be 4H or finer; the loader will resample/align to 4H.

## Run

From the repo root, run `python -m quant_system.main`.

## Notes

- No real exchange API calls are made.
- This is a research/backtest-style execution loop, not a live trading daemon.
