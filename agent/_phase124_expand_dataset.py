"""
agent/_phase124_expand_dataset.py — Historical Data Expansion Script for Phase 12.4

Fetches extended OHLCV candlestick data from Gate.io public futures endpoint
for all 12 configured assets and updates quant_system/data/csv/{asset}.csv.
Performs data integrity verification and reports candle statistics.
"""

import sys
import time
import requests
from pathlib import Path
import pandas as pd

ASSETS = [
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT", "AVAX_USDT",
    "LINK_USDT", "DOGE_USDT", "ADA_USDT", "LTC_USDT", "AAVE_USDT", "SUI_USDT"
]

CSV_DIR = Path("quant_system/data/csv")

def download_asset_candles(asset: str, interval: str = "4h", limit: int = 1000) -> pd.DataFrame:
    url = "https://fx-api.gateio.ws/api/v4/futures/usdt/candlesticks"
    params = {
        "contract": asset,
        "interval": interval,
        "limit": limit,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[{asset}] Gate API returned HTTP {resp.status_code}: {resp.text}")
            return pd.DataFrame()

        data = resp.json()
        if not data or not isinstance(data, list):
            print(f"[{asset}] Empty or invalid response")
            return pd.DataFrame()

        # Gate futures candlesticks structure:
        # t (timestamp sec), v (volume), c (close), h (high), l (low), o (open)
        rows = []
        for item in data:
            if isinstance(item, dict):
                t = int(item.get("t", 0))
                o = float(item.get("o", 0.0))
                h = float(item.get("h", 0.0))
                l = float(item.get("l", 0.0))
                c = float(item.get("c", 0.0))
                v = float(item.get("v", 0.0))
            elif isinstance(item, list) and len(item) >= 6:
                t = int(item[0])
                v = float(item[1])
                c = float(item[2])
                h = float(item[3])
                l = float(item[4])
                o = float(item[5])
            else:
                continue

            ts_iso = pd.to_datetime(t, unit="s", utc=True).isoformat()
            rows.append({
                "timestamp": ts_iso,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
        return df

    except Exception as e:
        print(f"[{asset}] Download failed: {e}")
        return pd.DataFrame()


def expand_all_datasets():
    print("=" * 80)
    print("PHASE 12.4 — HISTORICAL DATASET EXPANSION & INTEGRITY AUDIT")
    print("=" * 80)

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    integrity_summary = []

    for asset in ASSETS:
        print(f"Fetching 4H OHLCV candles for {asset}...")
        df_new = download_asset_candles(asset, interval="4h", limit=1000)
        time.sleep(0.2)

        csv_path = CSV_DIR / f"{asset}.csv"
        df_existing = pd.DataFrame()

        if csv_path.exists():
            try:
                df_existing = pd.read_csv(csv_path)
                if not df_existing.empty and "timestamp" in df_existing.columns:
                    df_existing["timestamp"] = pd.to_datetime(df_existing["timestamp"], utc=True)
            except Exception as e:
                print(f"Warning loading existing CSV for {asset}: {e}")

        # Combine existing and new
        if not df_existing.empty and not df_new.empty:
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        elif not df_new.empty:
            df_combined = df_new
        else:
            df_combined = df_existing

        if df_combined.empty:
            print(f"[{asset}] ERROR: No data available!")
            continue

        df_combined = df_combined.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
        df_combined["timestamp"] = pd.to_datetime(df_combined["timestamp"], utc=True)
        df_combined = df_combined.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

        # Integrity Checks
        candle_count = len(df_combined)
        start_ts = df_combined["timestamp"].iloc[0].isoformat()
        end_ts = df_combined["timestamp"].iloc[-1].isoformat()

        # Duplicate check
        dup_count = df_combined.duplicated(subset=["timestamp"]).sum()

        # Missing / Gap check
        time_diffs = df_combined["timestamp"].diff()
        expected_diff = pd.Timedelta(hours=4)
        gaps = (time_diffs > expected_diff * 1.5).sum()

        # Save to CSV
        df_combined["timestamp"] = df_combined["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df_combined[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(csv_path, index=False)

        status = "VALID" if candle_count >= 100 and dup_count == 0 and gaps == 0 else ("VALID_WITH_GAPS" if gaps > 0 else "SHORT_DATA")

        integrity_summary.append({
            "asset": asset,
            "candles": candle_count,
            "start": start_ts,
            "end": end_ts,
            "missing": 0,
            "duplicates": dup_count,
            "gaps": gaps,
            "status": status,
        })

    print("\n" + "=" * 80)
    print("HISTORICAL DATA INTEGRITY REPORT")
    print("=" * 80)
    print(f"{'Asset':<12} | {'Candles':<8} | {'Start':<22} | {'End':<22} | {'Gaps':<5} | {'Status':<15}")
    print("-" * 90)
    for r in integrity_summary:
        print(f"{r['asset']:<12} | {r['candles']:<8d} | {r['start'][:19]:<22} | {r['end'][:19]:<22} | {r['gaps']:<5d} | {r['status']:<15}")

if __name__ == "__main__":
    expand_all_datasets()
