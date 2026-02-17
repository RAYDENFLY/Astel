"""Minimal Gate.io Futures leverage set test.

Purpose:
- Let you reproduce the leverage-change call from Gate docs against your current
  API keys/secret and verify the response quickly.

Notes:
- Uses ENV vars: GATE_API_KEY, GATE_API_SECRET.
- Targets classic futures endpoint: POST /futures/usdt/positions/{contract}/leverage?leverage=10
- If you're actually using hedge/dual_comp mode, the endpoint differs.

Run:
  python scripts/gate_set_leverage_test.py --contract BTC_USDT --leverage 10

Optional:
  python scripts/gate_set_leverage_test.py --host https://fx-api-testnet.gateio.ws

"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import requests


def _sha512_hex(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def gen_sign(method: str, full_path: str, query_string: str, body: str = "") -> dict:
    """Generate Gate API v4 signature headers.

    Gate signing string is:
      method\npath\nquery\nsha512(body)\ntimestamp
    """

    key = os.getenv("GATE_API_KEY")
    secret = os.getenv("GATE_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Missing GATE_API_KEY/GATE_API_SECRET env vars")

    t = str(int(time.time()))
    body_hash = _sha512_hex(body.encode("utf-8"))
    s = "\n".join([method.upper(), full_path, query_string, body_hash, t])
    sign = hmac.new(secret.encode("utf-8"), s.encode("utf-8"), hashlib.sha512).hexdigest()

    return {"KEY": key, "Timestamp": t, "SIGN": sign}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="https://api.gateio.ws")
    ap.add_argument("--prefix", default="/api/v4")
    ap.add_argument("--contract", default="BTC_USDT")
    ap.add_argument("--leverage", type=int, default=10)
    ap.add_argument(
        "--endpoint",
        default="/futures/usdt/positions/{contract}/leverage",
        help="Change if you want dual_comp endpoint",
    )
    args = ap.parse_args()

    endpoint = args.endpoint.format(contract=args.contract)

    # Gate docs use query-string params for this endpoint
    query = urlencode({"leverage": str(int(args.leverage))})

    method = "POST"
    full_path = args.prefix + endpoint
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    headers.update(gen_sign(method, full_path, query, body=""))

    url = f"{args.host}{args.prefix}{endpoint}?{query}"

    r = requests.request(method, url, headers=headers, timeout=30)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw": r.text}

    print(json.dumps({"status": r.status_code, "response": payload}, indent=2))


if __name__ == "__main__":
    main()
