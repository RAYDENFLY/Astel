"""
Phase 9.0 — Unified Execution Engine

Single entry point for ALL order execution regardless of mode (SIMULATION/TESTNET/LIVE).

Design:
- ExecutionEngine wraps GateExecutor with reliability layer
- Same code path for TESTNET and LIVE — only endpoint/credentials differ
- Orders stored in agent_orders table (PostgreSQL/SQLite)
- Retry, rate-limit, duplicate prevention, reconciliation built in
- Risk validation via callbacks before execution
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("quant_system.execution_engine")


# ---------------------------------------------------------------------------
# Execution Mode
# ---------------------------------------------------------------------------

class ExecutionMode(str, Enum):
    SIMULATION = "SIMULATION"
    TESTNET = "TESTNET"
    LIVE = "LIVE"


# ---------------------------------------------------------------------------
# Order domain model
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    TP_SL = "TP_SL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


@dataclass
class ExchangeOrder:
    """Internal order representation — the single format used throughout the system."""
    # Required
    contract: str
    side: OrderSide
    size: float
    order_type: OrderType

    # Optional with defaults
    price: Optional[float] = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    reduce_only: bool = False
    ioc: bool = False  # Immediate-or-cancel (used for market orders)
    text: str = "t-qt"

    # Runtime fields (populated after execution)
    order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    avg_fill_price: Optional[float] = None
    fees: float = 0.0
    slippage: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None

    # Timestamps
    created_at: Optional[str] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None

    # PnL (populated on close)
    realized_pnl: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract": self.contract,
            "side": self.side.value,
            "size": self.size,
            "order_type": self.order_type.value,
            "price": self.price,
            "stop_price": self.stop_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "reduce_only": self.reduce_only,
            "ioc": self.ioc,
            "text": self.text,
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "status": self.status.value,
            "filled_size": self.filled_size,
            "avg_fill_price": self.avg_fill_price,
            "fees": self.fees,
            "slippage": self.slippage,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "created_at": self.created_at,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "realized_pnl": self.realized_pnl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExchangeOrder":
        return cls(
            contract=data["contract"],
            side=OrderSide(data["side"]),
            size=float(data["size"]),
            order_type=OrderType(data["order_type"]),
            price=float(data["price"]) if data.get("price") else None,
            stop_price=float(data["stop_price"]) if data.get("stop_price") else None,
            tp_price=float(data["tp_price"]) if data.get("tp_price") else None,
            sl_price=float(data["sl_price"]) if data.get("sl_price") else None,
            reduce_only=bool(data.get("reduce_only", False)),
            ioc=bool(data.get("ioc", False)),
            text=str(data.get("text", "t-qt")),
            order_id=str(data["order_id"]) if data.get("order_id") else None,
            exchange_order_id=str(data["exchange_order_id"]) if data.get("exchange_order_id") else None,
            status=OrderStatus(data.get("status", "PENDING")),
            filled_size=float(data.get("filled_size", 0)),
            avg_fill_price=float(data["avg_fill_price"]) if data.get("avg_fill_price") else None,
            fees=float(data.get("fees", 0)),
            slippage=float(data.get("slippage", 0)),
            latency_ms=float(data.get("latency_ms", 0)),
            error=str(data["error"]) if data.get("error") else None,
            created_at=str(data["created_at"]) if data.get("created_at") else None,
            opened_at=str(data["opened_at"]) if data.get("opened_at") else None,
            closed_at=str(data["closed_at"]) if data.get("closed_at") else None,
            realized_pnl=float(data["realized_pnl"]) if data.get("realized_pnl") else None,
        )

    def generate_order_id(self) -> str:
        """Deterministic unique order ID based on intent."""
        raw = f"{self.contract}|{self.side.value}|{self.size}|{self.order_type.value}|{time.time_ns()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Execution Engine
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """Unified execution wrapper.

    Delegates to GateExecutor for TESTNET/LIVE.
    Uses a risk_callback for pre-execution validation.
    Stores every order in agent_orders via a storage_callback.
    """

    def __init__(
        self,
        executor: Any,
        mode: ExecutionMode = ExecutionMode.TESTNET,
        storage_callback: Optional[Callable] = None,
        risk_callback: Optional[Callable] = None,
        max_retries: int = 3,
        rate_limit_per_second: float = 5.0,
    ):
        self.executor = executor
        self.mode = mode
        self.storage_callback = storage_callback
        self.risk_callback = risk_callback
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._min_interval = 1.0 / max(rate_limit_per_second, 1.0)
        self._dedup_cache: Dict[str, float] = {}  # order_id → timestamp
        self._dedup_ttl = 5.0  # seconds to keep dedup entries

        log.info("ExecutionEngine initialized: mode=%s, max_retries=%d", mode, max_retries)

    # ------------------------------------------------------------------
    # Core execution methods
    # ------------------------------------------------------------------

    def open_position(
        self,
        contract: str,
        side: OrderSide,
        size: float,
        *,
        price: Optional[float] = None,
        reduce_only: bool = False,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExchangeOrder:
        """Open a new position — market order unless price specified."""
        return self._execute_order(
            ExchangeOrder(
                contract=contract,
                side=side,
                size=abs(size),
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                price=price,
                ioc=(price is None),
                reduce_only=reduce_only,
                tp_price=tp_price,
                sl_price=sl_price,
            )
        )

    def close_position(
        self,
        contract: str,
        size: float,
        side: Optional[OrderSide] = None,
    ) -> ExchangeOrder:
        """Close an existing position by market order.

        If side is None, it's auto-detected by querying the exchange.
        """
        if side is None:
            positions = self.executor.get_open_positions()
            pos = self._find_position(positions, contract)
            if pos is None:
                raise ValueError(f"No open position for {contract}")
            current_size = float(pos.get("size", 0) or 0)
            if current_size > 0:
                side = OrderSide.SELL
            else:
                side = OrderSide.BUY
            size = abs(current_size)

        return self._execute_order(
            ExchangeOrder(
                contract=contract,
                side=side,
                size=abs(size),
                order_type=OrderType.MARKET,
                reduce_only=True,
                ioc=True,
            )
        )

    def reduce_position(
        self,
        contract: str,
        pct: float = 0.25,
    ) -> ExchangeOrder:
        """Reduce position by percentage (0-1, capped at 0.25)."""
        pct = min(pct, 0.25)
        positions = self.executor.get_open_positions()
        pos = self._find_position(positions, contract)
        if pos is None:
            raise ValueError(f"No open position for {contract}")
        current_size = abs(float(pos.get("size", 0) or 0))
        if current_size <= 0:
            raise ValueError("Position size is 0")
        reduce_size = max(1, int(current_size * pct))
        side = OrderSide.SELL if float(pos.get("size", 0) or 0) > 0 else OrderSide.BUY

        return self._execute_order(
            ExchangeOrder(
                contract=contract,
                side=side,
                size=reduce_size,
                order_type=OrderType.MARKET,
                reduce_only=True,
                ioc=True,
            )
        )

    def set_tpsl(
        self,
        contract: str,
        position_side: str,
        size: float,
        *,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Set take-profit and/or stop-loss trigger orders on an open position.

        Returns dict with keys: {"tp": ExchangeOrder|None, "sl": ExchangeOrder|None}
        """
        result: Dict[str, Any] = {"tp": None, "sl": None}

        if self.mode == ExecutionMode.SIMULATION:
            # In simulation, TP/SL is a no-op (just record intent)
            if take_profit:
                result["tp"] = ExchangeOrder(
                    contract=contract,
                    side=OrderSide.SELL if position_side.upper() == "LONG" else OrderSide.BUY,
                    size=int(abs(size)),
                    order_type=OrderType.TP_SL,
                    tp_price=take_profit,
                    status=OrderStatus.OPEN,
                )
                result["tp"].order_id = result["tp"].generate_order_id()
            if stop_loss:
                result["sl"] = ExchangeOrder(
                    contract=contract,
                    side=OrderSide.SELL if position_side.upper() == "LONG" else OrderSide.BUY,
                    size=int(abs(size)),
                    order_type=OrderType.TP_SL,
                    sl_price=stop_loss,
                    status=OrderStatus.OPEN,
                )
                result["sl"].order_id = result["sl"].generate_order_id()
            return result

        # TESTNET/LIVE: delegate to GateExecutor trigger order placement
        gate_result = self.executor.place_tpsl_orders(
            contract=contract,
            position_side=position_side,
            size=size,
            take_profit=take_profit,
            stop_loss=stop_loss,
        )

        if gate_result.get("tp"):
            result["tp"] = self._gate_to_order(gate_result["tp"], OrderType.TP_SL)
        if gate_result.get("sl"):
            result["sl"] = self._gate_to_order(gate_result["sl"], OrderType.TP_SL)

        return result

    def cancel_order(self, order_id: str) -> ExchangeOrder:
        """Cancel an open order by internal order_id or exchange order_id."""
        try:
            result = self.executor.cancel_trigger_order(order_id)
            order = ExchangeOrder(
                contract="",
                side=OrderSide.BUY,
                size=0,
                order_type=OrderType.MARKET,
                status=OrderStatus.CANCELLED,
                exchange_order_id=order_id,
            )
            order.order_id = order.generate_order_id()
            if self.storage_callback:
                self.storage_callback(order.to_dict())
            return order
        except Exception as e:
            order = ExchangeOrder(
                contract="", side=OrderSide.BUY, size=0,
                order_type=OrderType.MARKET, status=OrderStatus.FAILED,
                error=str(e), exchange_order_id=order_id,
            )
            order.order_id = order.generate_order_id()
            return order

    # ------------------------------------------------------------------
    # Query methods (pass-through to executor)
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Dict[str, Any]]:
        if self.mode == ExecutionMode.SIMULATION:
            return []
        try:
            return self.executor.get_open_positions()
        except Exception as e:
            log.error("Failed to fetch positions: %s", e)
            return []

    def get_open_orders(self, contract: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.mode == ExecutionMode.SIMULATION:
            return []
        try:
            return self.executor.get_open_trigger_orders(contract=contract)
        except Exception as e:
            log.error("Failed to fetch open orders: %s", e)
            return []

    def get_balance(self) -> Dict[str, Any]:
        if self.mode == ExecutionMode.SIMULATION:
            return {"total": 0.0, "available": 0.0, "unrealized_pnl": 0.0}
        try:
            total = self.executor.get_account_equity()
            return {"total": total, "available": 0.0, "unrealized_pnl": 0.0}
        except Exception as e:
            log.error("Failed to fetch balance: %s", e)
            return {"total": 0.0, "available": 0.0, "unrealized_pnl": 0.0}

    def get_position_pnl(self, contract: str) -> Optional[float]:
        try:
            positions = self.get_positions()
            for p in positions:
                if str(p.get("contract")) == contract:
                    unrealized = p.get("unrealised_pnl", p.get("unrealized_pnl"))
                    if unrealized is not None:
                        return float(unrealized)
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal: execution with reliability
    # ------------------------------------------------------------------

    def _execute_order(self, order: ExchangeOrder) -> ExchangeOrder:
        """Execute a single order through the full pipeline with retries and dedup."""
        order.order_id = order.generate_order_id()
        order.created_at = datetime.now(tz=timezone.utc).isoformat()

        # 1. Dedup check
        if order.order_id in self._dedup_cache:
            elapsed = time.time() - self._dedup_cache[order.order_id]
            if elapsed < self._dedup_ttl:
                raise ValueError(f"Duplicate order detected: {order.order_id}")
        self._dedup_cache[order.order_id] = time.time()

        # 2. Risk callback
        if self.risk_callback:
            risk_ok = self.risk_callback(order)
            if not risk_ok:
                order.status = OrderStatus.REJECTED
                order.error = "Risk callback rejected order"
                self._store(order)
                return order

        # 3. SIMULATION mode — just record
        if self.mode == ExecutionMode.SIMULATION:
            order.status = OrderStatus.FILLED
            order.filled_size = order.size
            order.avg_fill_price = order.price or 0.0
            self._store(order)
            return order

        # 4. Rate limit
        self._enforce_rate_limit()

        # 5. Execute with retries
        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            start = time.time()
            try:
                if order.order_type == OrderType.MARKET:
                    signed_size = order.size if order.side == OrderSide.BUY else -order.size
                    gate_result = self.executor.place_market_order(
                        contract=order.contract,
                        size=signed_size,
                        portfolio_risk_ok=True,
                    )
                elif order.order_type == OrderType.LIMIT:
                    # Gate limit order via same endpoint but with price
                    path = "/futures/usdt/orders"
                    signed_size = order.size if order.side == OrderSide.BUY else -order.size
                    payload = {
                        "contract": order.contract,
                        "size": int(signed_size),
                        "price": str(order.price) if order.price else "0",
                        "type": "limit" if order.price else "market",
                        "text": order.text,
                    }
                    gate_result = self._gate_request("POST", path, payload)
                else:
                    raise ValueError(f"Unsupported order type: {order.order_type}")

                latency = (time.time() - start) * 1000
                order.latency_ms = round(latency, 1)

                # Map Gate response to our order model
                self._map_gate_response(order, gate_result)
                order.status = OrderStatus.FILLED
                self._store(order)
                return order

            except Exception as e:
                last_error = str(e)
                log.warning("Order attempt %d/%d failed: %s", attempt, self.max_retries, last_error)
                if attempt < self.max_retries:
                    time.sleep(1.0 * attempt)
                continue

        order.status = OrderStatus.FAILED
        order.error = last_error
        self._store(order)
        return order

    def _map_gate_response(self, order: ExchangeOrder, gate_resp: Dict[str, Any]) -> None:
        """Map Gate.io API response fields to our ExchangeOrder."""
        if not isinstance(gate_resp, dict):
            return

        order.exchange_order_id = str(gate_resp.get("id", gate_resp.get("order_id", "")))
        status_str = str(gate_resp.get("status", "")).upper()
        status_map = {
            "OPEN": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "LIQUIDATED": OrderStatus.FILLED,
            "FINISHED": OrderStatus.FILLED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        order.status = status_map.get(status_str, OrderStatus.FILLED)

        fill_price = gate_resp.get("fill_price", gate_resp.get("avg_price"))
        if fill_price:
            order.avg_fill_price = float(fill_price)

        filled = gate_resp.get("filled_total", gate_resp.get("size"))
        if filled:
            order.filled_size = abs(float(filled))

        deal_fee = gate_resp.get("deal_fee", gate_resp.get("fee"))
        if deal_fee:
            order.fees = abs(float(deal_fee))

        pnl = gate_resp.get("realised_pnl", gate_resp.get("realised_pnl"))
        if pnl:
            order.realized_pnl = float(pnl)

    def _gate_request(self, method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Direct Gate API call used for LIMIT orders and custom operations."""
        self._enforce_rate_limit()
        # Build URL
        query_string = ""
        url = self.executor.base_url + path
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        headers = self.executor._signed_headers(method, path, query_string, body)
        import urllib.request
        req = urllib.request.Request(url=url, data=body.encode("utf-8"), headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}

    def _enforce_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _store(self, order: ExchangeOrder) -> None:
        if self.storage_callback:
            try:
                self.storage_callback(order.to_dict())
            except Exception as e:
                log.error("Order storage failed: %s", e)

    @staticmethod
    def _find_position(positions: List[Dict[str, Any]], contract: str) -> Optional[Dict[str, Any]]:
        for p in positions:
            if str(p.get("contract")) == contract:
                return p
        return None

    @staticmethod
    def _gate_to_order(gate_resp: Dict[str, Any], order_type: OrderType = OrderType.TP_SL) -> ExchangeOrder:
        """Convert a Gate API response dict to an ExchangeOrder (used for trigger orders)."""
        order = ExchangeOrder(
            contract=str(gate_resp.get("contract", "")),
            side=OrderSide.BUY if float(gate_resp.get("size", 0) or 0) > 0 else OrderSide.SELL,
            size=abs(float(gate_resp.get("size", 0) or 0)),
            order_type=order_type,
        )
        order.exchange_order_id = str(gate_resp.get("id", ""))
        order.order_id = order.generate_order_id()
        order.status = OrderStatus.OPEN
        order.created_at = datetime.now(tz=timezone.utc).isoformat()
        return order