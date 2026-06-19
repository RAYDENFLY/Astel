"""
agent/shadow.py — Shadow Mode: compare agent recommendations vs actual system behavior.

Phase 2: No exchange actions, no GateExecutor integration, no trading.
Read-only observation + comparison + measurement.

Comparison logic:
  - Snapshot exchange state BEFORE and AFTER each observation window
  - Detect if position size changed, TP/SL changed, pause flags changed
  - Determine agreement/disagreement with agent recommendation
  - After 24h, resolve with objective market measurements (not subjective rules)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import ActionType, AgentPlan, AgentSnapshot
from agent.storage import AgentStorage

log = logging.getLogger("agent.shadow")


# ---------------------------------------------------------------------------
# Exchange state snapshot (read-only, no GateExecutor needed)
# ---------------------------------------------------------------------------

class ExchangeSnapshot:
    """
    Read-only snapshot of exchange state at a point in time.
    Data sources:
      - Dashboard API for positions and account
      - Runner flags file for pause state
      - Config file for risk params
    """

    def __init__(
        self,
        positions: List[Dict[str, Any]],
        pause_entries: bool,
        risk_config: Dict[str, Any],
        account_equity: float,
        drawdown_pct: float,
    ) -> None:
        self.positions = positions
        self.pause_entries = pause_entries
        self.risk_config = risk_config
        self.account_equity = account_equity
        self.drawdown_pct = drawdown_pct
        self.ts = datetime.now(tz=timezone.utc)

    def get_position(self, contract: str) -> Optional[Dict[str, Any]]:
        for p in self.positions:
            if str(p.get("contract", "")) == contract:
                return p
        return None

    def get_position_size(self, contract: str) -> float:
        pos = self.get_position(contract)
        if pos is None:
            return 0.0
        try:
            return float(pos.get("size", 0) or 0)
        except Exception:
            return 0.0


def _fetch_exchange_snapshot(
    dashboard_base_url: str,
    runner_flags_path: str,
    config_path: str,
) -> ExchangeSnapshot:
    """
    Fetch current exchange state from dashboard API + local files.
    No GateExecutor calls. Read-only.
    """
    import requests
    import yaml
    import os

    # Positions from dashboard
    positions: List[Dict[str, Any]] = []
    try:
        resp = requests.get(
            f"{dashboard_base_url}/api/open-positions", timeout=10
        )
        if resp.status_code == 200:
            raw = resp.json()
            if isinstance(raw, dict):
                positions = raw.get("positions", []) or []
            elif isinstance(raw, list):
                positions = raw
    except Exception as e:
        log.warning("Shadow: failed to fetch positions: %s", e)

    # Account equity + drawdown from dashboard
    equity = 0.0
    drawdown = 0.0
    try:
        resp = requests.get(f"{dashboard_base_url}/api/account", timeout=10)
        if resp.status_code == 200:
            acct = resp.json()
            equity = float(acct.get("equity", 0) or 0)
            dd_raw = float(acct.get("drawdown", 0) or 0)
            # Convert fraction to negative percentage
            if dd_raw > 0:
                drawdown = -round(dd_raw * 100.0, 2)
    except Exception as e:
        log.warning("Shadow: failed to fetch account: %s", e)

    # PAUSE_ENTRIES flag from runner flags file
    pause_entries = False
    try:
        if os.path.exists(runner_flags_path):
            with open(runner_flags_path, "r", encoding="utf-8") as f:
                flags = yaml.safe_load(f) or {}
            pause_entries = bool(flags.get("pause_entries", False))
    except Exception:
        pass

    # Risk config from config.yaml
    risk_config: Dict[str, Any] = {}
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            risk_config = cfg.get("risk", {})
    except Exception:
        pass

    return ExchangeSnapshot(
        positions=positions,
        pause_entries=pause_entries,
        risk_config=risk_config,
        account_equity=equity,
        drawdown_pct=drawdown,
    )


# ---------------------------------------------------------------------------
# Agreement detection (per action type)
# ---------------------------------------------------------------------------

def _detect_agreement(
    action_type: ActionType,
    action_params: Dict[str, Any],
    before: ExchangeSnapshot,
    after: ExchangeSnapshot,
) -> Tuple[str, str]:
    """
    Compare agent recommendation vs actual system behavior.
    Returns (agreement: str, system_action: str).
    
    agreement values: AGREE | DISAGREE | PARTIAL | NOT_APPLICABLE | UNKNOWN
    """
    contract = action_params.get("contract", "")

    if action_type == ActionType.PAUSE_ENTRIES:
        if after.pause_entries:
            return "AGREE", "System paused entries as recommended"
        if not before.pause_entries and not after.pause_entries:
            return "DISAGREE", "System did not pause entries"
        return "PARTIAL", "Pause state changed unexpectedly"

    elif action_type == ActionType.RESUME_ENTRIES:
        if not after.pause_entries and before.pause_entries:
            return "AGREE", "System resumed entries as recommended"
        if after.pause_entries:
            return "DISAGREE", "System kept entries paused"
        return "PARTIAL", "Resume state ambiguous"

    elif action_type == ActionType.TIGHTEN_RISK:
        atr_changed = False
        rpt_changed = False
        if "atr_multiplier" in action_params:
            recommended = float(action_params["atr_multiplier"])
            actual = float(after.risk_config.get("atr_multiplier", 0) or 0)
            atr_changed = abs(actual - recommended) < 0.01
        if "risk_per_trade" in action_params:
            recommended = float(action_params["risk_per_trade"])
            actual = float(after.risk_config.get("risk_per_trade", 0) or 0)
            rpt_changed = abs(actual - recommended) < 0.0001
        if atr_changed or rpt_changed:
            return "AGREE", "Risk params updated as recommended"
        return "DISAGREE", "Risk params not updated"

    elif action_type == ActionType.REDUCE_POSITION:
        if not contract:
            return "NOT_APPLICABLE", "No contract specified"
        size_before = before.get_position_size(contract)
        size_after = after.get_position_size(contract)
        if abs(size_after) < abs(size_before):
            return "AGREE", f"Position reduced: {abs(size_before)} → {abs(size_after)}"
        if abs(size_after) == abs(size_before):
            return "DISAGREE", f"Position size unchanged: {abs(size_before)}"
        return "PARTIAL", f"Position changed: {abs(size_before)} → {abs(size_after)}"

    elif action_type == ActionType.CLOSE_POSITION:
        if not contract:
            return "NOT_APPLICABLE", "No contract specified"
        size_before = before.get_position_size(contract)
        size_after = after.get_position_size(contract)
        if size_after == 0.0 and size_before != 0.0:
            return "AGREE", f"Position closed: {abs(size_before)} → 0"
        if abs(size_after) >= abs(size_before):
            return "DISAGREE", f"Position not closed: {abs(size_before)} → {abs(size_after)}"
        return "PARTIAL", f"Position reduced but not closed: {abs(size_before)} → {abs(size_after)}"

    elif action_type in (ActionType.REPLACE_TPSL, ActionType.CANCEL_STALE_TPSL):
        if not contract:
            return "NOT_APPLICABLE", "No contract specified"
        size_before = before.get_position_size(contract)
        size_after = after.get_position_size(contract)
        # Best-effort: if position size changed, TP/SL likely changed with it
        if abs(size_before - size_after) > 0.01:
            return "AGREE", f"Position changed; TP/SL likely adjusted"
        # Check from risk config (imperfect proxy)
        return "UNKNOWN", "Cannot directly observe TP/SL changes via API"

    elif action_type == ActionType.SET_SURVIVAL_MODE:
        # Always N/A — internal agent state, not system behavior
        return "NOT_APPLICABLE", "Internal agent state change"

    elif action_type == ActionType.NOTIFY:
        return "NOT_APPLICABLE", "Notification has no system impact"

    elif action_type == ActionType.ROTATE_LOGS:
        return "NOT_APPLICABLE", "Log rotation has no observable system impact"

    elif action_type == ActionType.EXPORT_REPORT:
        return "NOT_APPLICABLE", "Report export has no observable system impact"

    elif action_type == ActionType.UPDATE_CONFIG:
        # Check if config actually changed
        changes = 0
        for key, value in action_params.items():
            parts = key.split(".", 1)
            if len(parts) == 2:
                section, field = parts
                actual_value = after.risk_config.get(field) if section == "risk" else None
                if actual_value is not None and str(actual_value) == str(value):
                    changes += 1
        if changes > 0:
            return "AGREE", f"{changes} config key(s) updated"
        return "DISAGREE", "Config not updated as recommended"

    elif action_type == ActionType.REVERSE_POSITION:
        if not contract:
            return "NOT_APPLICABLE", "No contract specified"
        size_before = before.get_position_size(contract)
        size_after = after.get_position_size(contract)
        # Reversal = flipped sign
        if size_before * size_after < 0:
            return "AGREE", f"Position reversed: {size_before} → {size_after}"
        if abs(size_after) == 0:
            return "PARTIAL", f"Position closed but not reversed: {size_before} → 0"
        return "DISAGREE", f"Position not reversed: {size_before} → {size_after}"

    return "UNKNOWN", "No comparison logic for this action type"


# ---------------------------------------------------------------------------
# Shadow Comparator — main class
# ---------------------------------------------------------------------------

class ShadowComparator:
    """
    Compare agent recommendations against actual system behavior.
    
    - observe(): Called after each plan generation. Captures state BEFORE
      and AFTER the observation window, determines agreement, stores to DB.
    - resolve_pending(): Called on each tick. Finds observations older than
      24h and resolves them with objective market measurements.
    
    No exchange write operations. No GateExecutor. Read-only.
    """

    def __init__(
        self,
        storage: AgentStorage,
        dashboard_base_url: str,
        runner_flags_path: str = "agent/.runner_flags.yaml",
        config_path: str = "quant_system/config.yaml",
        observation_window_sec: int = 60,
    ) -> None:
        self._storage = storage
        self._dashboard_base_url = dashboard_base_url
        self._runner_flags_path = runner_flags_path
        self._config_path = config_path
        self._observation_window_sec = observation_window_sec

    def observe(
        self,
        plan: AgentPlan,
        plan_id: int,
    ) -> List[int]:
        """
        Compare agent plan against actual system behavior.
        
        1. Snapshot exchange state BEFORE (positions, pause flag, risk config)
        2. Wait for observation window
        3. Snapshot exchange state AFTER
        4. For each recommended action, detect agreement
        5. Store observations to DB
        
        Returns list of observation IDs created.
        """
        if not plan.proposed_actions:
            return []

        # Step 1: Snapshot BEFORE
        log.info(
            "Shadow: observing plan_id=%d with %d actions (window=%ds)",
            plan_id, len(plan.proposed_actions), self._observation_window_sec,
        )
        before = _fetch_exchange_snapshot(
            self._dashboard_base_url,
            self._runner_flags_path,
            self._config_path,
        )

        # Step 2: Wait for observation window
        time.sleep(self._observation_window_sec)

        # Step 3: Snapshot AFTER
        after = _fetch_exchange_snapshot(
            self._dashboard_base_url,
            self._runner_flags_path,
            self._config_path,
        )

        # Step 4 + 5: Detect agreement and store
        observation_ids: List[int] = []
        now = datetime.now(tz=timezone.utc)

        for action in plan.proposed_actions:
            agreement, system_action = _detect_agreement(
                action.type, action.params, before, after
            )

            contract = action.params.get("contract", "")
            size_before = before.get_position_size(contract) if contract else 0.0
            size_after = after.get_position_size(contract) if contract else 0.0

            obs_id = self._storage.save_shadow_observation(
                plan_id=plan_id,
                ts=now,
                recommended_action=action.type.value,
                recommended_params=json.dumps(action.params),
                contract=contract or None,
                survival_mode=plan.observations[0] if plan.observations else "NORMAL",
                system_action=system_action,
                position_size_before=size_before,
                position_size_after=size_after,
                tpsl_changed=0,  # Cannot directly observe via read-only API
                entries_paused=1 if after.pause_entries else 0,
                agreement=agreement,
                status="PENDING_24H",
                equity_at_obs=after.account_equity,
                drawdown_at_obs=after.drawdown_pct,
            )
            observation_ids.append(obs_id)

            log.info(
                "Shadow: action=%s contract=%s agreement=%s system_action=%s",
                action.type.value, contract or "(global)", agreement, system_action,
            )

        return observation_ids

    def resolve_pending(self) -> int:
        """
        Find all PENDING_24H observations older than 24h and resolve them.
        
        Resolution uses objective market measurements:
        - equity_24h_after: account equity at resolution time
        - asset_return_24h: proxy return from equity change
        - equity_change_24h: absolute equity change
        - counterfactual_pnl: estimated if agent recommendation was followed
          (null — cannot compute without execution)
        
        Returns count of observations resolved.
        """
        pending = self._storage.get_pending_shadow_observations()
        if not pending:
            return 0

        now = datetime.now(tz=timezone.utc)
        resolved_count = 0

        # Fetch current account state for resolution
        current_equity = 0.0
        try:
            import requests
            resp = requests.get(
                f"{self._dashboard_base_url}/api/account", timeout=10
            )
            if resp.status_code == 200:
                acct = resp.json()
                current_equity = float(acct.get("equity", 0) or 0)
        except Exception:
            log.warning("Shadow resolve: cannot fetch current equity")

        for obs in pending:
            obs_ts_str = obs.get("ts", "")
            try:
                obs_ts = datetime.fromisoformat(obs_ts_str)
            except Exception:
                continue

            # Check if 24h has elapsed
            if now - obs_ts < timedelta(hours=24):
                continue

            equity_at_obs = obs.get("equity_at_obs") or 0.0
            equity_change = current_equity - equity_at_obs if current_equity > 0 else None
            asset_return = (equity_change / equity_at_obs) if equity_at_obs > 0 and equity_change is not None else None

            # Update with resolution data
            resolved_count += 1
            self._storage.update_shadow_observation(
                obs_id=obs["id"],
                resolved_at=now,
                equity_24h_after=current_equity if current_equity > 0 else None,
                asset_return_24h=asset_return,
                equity_change_24h=equity_change,
                counterfactual_pnl=None,  # Cannot compute without execution
            )

            log.info(
                "Shadow resolved: obs_id=%d equity_change=%s asset_return=%s",
                obs["id"], equity_change, asset_return,
            )

        return resolved_count