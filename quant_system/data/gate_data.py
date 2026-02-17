"""Gate.io futures data fetcher.

This fetcher pulls historical OHLCV candles directly from Gate API v4:
  GET /futures/usdt/candlesticks

It returns the same unified long-format DataFrame shape as DataFetcher:
  timestamp, asset, open, high, low, close, volume

Notes:
- Candles returned by Gate can include the currently forming candle; callers that
  care about closed candles should drop the latest timestamp.
- Gate's response fields are typically: t, o, h, l, c, v, sum (strings).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from quant_system.execution.gate_executor import GateExecutor


@dataclass
class GateDataFetcher:
    cfg: Dict
    executor: GateExecutor

    def __post_init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)

    def load_ohlcv(
        self,
        *,
        limit: Optional[int] = None,
        exclude_last_open_candle: bool = True,
        persist_to_csv: bool = True,
    ) -> pd.DataFrame:
        assets: List[str] = list(self.cfg["assets"])
        timeframe: str = str(self.cfg["system"]["timeframe"]).upper()

        interval = self._interval_from_timeframe(timeframe)

        # Default: fetch as many as Gate allows in a single call (best-effort).
        if limit is None:
            limit = int(self.cfg.get("data", {}).get("gate", {}).get("candles_limit", 2000))

        # Optional: filter to contracts that actually exist (useful on testnet where many alts aren't listed).
        try:
            contracts = self.executor._request_json("GET", "/futures/usdt/contracts", params=None, payload=None)
            contract_names = {c.get("name") for c in contracts if isinstance(c, dict) and c.get("name")}
        except Exception:
            contract_names = set()

        if contract_names:
            missing = [a for a in assets if a not in contract_names]
            if missing:
                self._log.warning(
                    "Some configured assets are not available on this Gate environment and will be skipped: %s",
                    ", ".join(missing),
                )
            assets = [a for a in assets if a in contract_names]

        frames: List[pd.DataFrame] = []
        for asset in assets:
            try:
                raw = self.executor.get_futures_candlesticks(contract=asset, interval=interval, limit=int(limit))
            except Exception as e:
                # Some Gate listings may use a slightly different contract name.
                # Best-effort retry: remove underscores (ARB_USDT -> ARBUSDT).
                alt = asset.replace("_", "")
                if alt != asset:
                    try:
                        raw = self.executor.get_futures_candlesticks(
                            contract=alt, interval=interval, limit=int(limit)
                        )
                        asset = alt  # store under the actual contract name we queried
                    except Exception:
                        self._log.warning("Failed fetching candles for %s: %s", asset, e)
                        continue
                else:
                    self._log.warning("Failed fetching candles for %s: %s", asset, e)
                    continue

            df = self._candles_to_df(raw)
            if df.empty:
                self._log.warning("No candle data returned for %s", asset)
                continue

            # Ensure UTC timestamps
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp")

            if exclude_last_open_candle and len(df) >= 2:
                # Drop latest candle because it may be in-progress.
                df = df.iloc[:-1].copy()

            df["asset"] = asset
            frames.append(df)

            if persist_to_csv:
                self._persist_asset_csv(asset=asset, df=df)

            # Be polite to the public endpoint.
            time.sleep(float(self.cfg.get("data", {}).get("gate", {}).get("request_sleep_sec", 0.12)))

        if not frames:
            raise ValueError("No OHLCV data loaded from Gate. Check symbols, interval, and connectivity.")

        out = pd.concat(frames, ignore_index=True)
        out = out[["timestamp", "asset", "open", "high", "low", "close", "volume"]]
        out = out.sort_values(["timestamp", "asset"]).reset_index(drop=True)
        return out

    def _persist_asset_csv(self, *, asset: str, df: pd.DataFrame) -> None:
        """Upsert candles into quant_system/data/csv/{ASSET}.csv.

        We keep a local base dataset so future runs can train offline too.
        This method is best-effort and never fails the main fetch.
        """
        try:
            csv_dir = Path(self.cfg.get("data", {}).get("csv_dir", "quant_system/data/csv"))
            csv_dir.mkdir(parents=True, exist_ok=True)
            fp = csv_dir / f"{asset}.csv"

            out = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)

            if fp.exists():
                try:
                    old = pd.read_csv(fp)
                    if not old.empty:
                        old.columns = [c.strip().lower() for c in old.columns]
                        if "timestamp" in old.columns:
                            old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True, errors="coerce")
                        old = old[["timestamp", "open", "high", "low", "close", "volume"]]
                        out = pd.concat([old, out], ignore_index=True)
                except Exception:
                    # If existing CSV is malformed, overwrite with the fresh dataset.
                    pass

            out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
            out = out.drop_duplicates(subset=["timestamp"], keep="last")
            out = out.sort_values("timestamp")

            # Store timestamp as ISO8601 for pandas friendliness.
            out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            out.to_csv(fp, index=False)
        except Exception as e:
            self._log.warning("Failed persisting CSV for %s: %s", asset, e)

    @staticmethod
    def _candles_to_df(raw: List[Dict]) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        def _f(x):
            try:
                return float(x)
            except Exception:
                return float("nan")

        rows = []
        for c in raw:
            # Gate usually returns timestamps in seconds.
            t = c.get("t")
            try:
                ts = int(t)
            except Exception:
                continue

            rows.append(
                {
                    "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                    "open": _f(c.get("o")),
                    "high": _f(c.get("h")),
                    "low": _f(c.get("l")),
                    "close": _f(c.get("c")),
                    "volume": _f(c.get("v")),
                }
            )

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df = df.dropna(subset=["open", "high", "low", "close"])
        return df

    @staticmethod
    def _interval_from_timeframe(timeframe: str) -> str:
        tf = timeframe.upper()
        if tf == "4H":
            return "4h"
        if tf == "1H":
            return "1h"
        if tf == "1D":
            return "1d"
        raise ValueError(f"Unsupported timeframe for Gate interval mapping: {timeframe}")
