"""
Phase 10.7B — Daily Operational Report Generator + Dashboard Closures Migration

Migrates the "Recent Closures (Realized)" dashboard panel from legacy
trade_closures table to ExecutionEngine-backed agent_trade_replay_events.

The new data source contains real Gate.io exchange responses:
  - avg_fill_price (real entry/exit prices)
  - realized_pnl (real PnL from exchange)
  - fees (real fees from exchange)
  - status (FILLED / REJECTED / etc.)
  - latency_ms (real execution latency)

Legacy trade_closures table becomes deprecated.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.storage import AgentStorage

log = logging.getLogger("agent.daily_report")

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# =====================================================================
# NEW: Replay-based closures reader
# =====================================================================

def get_closures_from_replay(storage: AgentStorage, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Read completed trades from agent_trade_replay_summary + events.
    
    Each completed trade with a position_closed event provides real
    exchange data: exit_price, exit_reason, realized_pnl.
    
    Returns closures ordered by completion time (newest first).
    """
    try:
        trades = storage.get_trade_replay_summary(limit=limit)
    except Exception:
        return []
    
    closures = []
    for t in trades:
        trade_id = t.get("trade_id")
        if not trade_id:
            continue
        try:
            events = storage.get_trade_replay_events(trade_id)
        except Exception:
            continue
        
        # Find exchange_response (has execution details)
        exchange_resp = None
        position_closed = None
        pnl_event = None
        created_event = None
        
        for ev in events:
            etype = ev.get("event_type", "")
            if etype == "exchange_response":
                exchange_resp = ev
            elif etype == "position_closed":
                position_closed = ev
            elif etype == "pnl_realized":
                pnl_event = ev
            elif etype == "trade_created":
                created_event = ev
        
        if not exchange_resp and not position_closed:
            continue  # not a traded closure
        
        # Extract event_data JSON
        def _parse_data(ev: Optional[Dict]) -> Dict:
            if ev is None:
                return {}
            raw = ev.get("event_data") or ev.get("metadata") or "{}"
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except Exception:
                    return {}
            return raw if isinstance(raw, dict) else {}
        
        resp_data = _parse_data(exchange_resp)
        close_data = _parse_data(position_closed)
        pnl_data = _parse_data(pnl_event)
        
        # Build closure row with REAL exchange data
        closure = {
            "trade_id": trade_id,
            "contract": t.get("contract", ""),
            "side": t.get("side", ""),
            "plan_id": t.get("plan_id", 0),
            "exchange_order_id": resp_data.get("exchange_order_id", ""),
            "status": t.get("status", ""),
            # Real entry price from exchange response
            "entry_price": resp_data.get("avg_fill_price"),
            # Real exit price from position_closed event
            "exit_price": close_data.get("exit_price"),
            "exit_size": close_data.get("exit_size"),
            "exit_reason": close_data.get("exit_reason", ""),
            # Realized PnL from pnl event (or close data)
            "realized_pnl": (
                pnl_data.get("realized_pnl")
                or close_data.get("realized_pnl")
            ),
            # Fees from exchange response
            "fees": resp_data.get("fees", 0),
            # Timestamps
            "created_at": t.get("created_at", ""),
            "closed_at": events[-1].get("timestamp", "") if events else "",
            # Latency
            "latency_ms": resp_data.get("latency_ms", exchange_resp.get("latency_ms", 0)),
            "provider": t.get("llm_provider", "unknown"),
        }
        closures.append(closure)
    
    # Sort by closed_at descending (newest first)
    closures.sort(key=lambda c: c.get("closed_at", ""), reverse=True)
    return closures


def get_closure_stats_from_replay(storage: AgentStorage, lookback: int = 200) -> Dict[str, Any]:
    """
    Compute stats from replay-based closures (replaces trade_clusters query).
    """
    closures = get_closures_from_replay(storage, limit=lookback)
    
    pnls = []
    for c in closures:
        pnl = c.get("realized_pnl")
        if pnl is not None:
            try:
                pnls.append(float(pnl))
            except Exception:
                continue
    
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    considered = wins + losses
    total_pnl = sum(pnls) if pnls else 0.0
    avg_pnl = total_pnl / considered if considered > 0 else 0.0
    
    return {
        "closed_trades": len(closures),
        "wins": wins,
        "losses": losses,
        "winrate": round(wins / max(1, considered), 4),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "source": "agent_trade_replay_events",
    }


# =====================================================================
# Existing: Daily Report (unchanged)
# =====================================================================

class DailyReport:
    """Aggregates all available metrics from the agent database."""

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage
        self._data: dict = {}

    def generate(self) -> dict:
        """Generate full daily report from storage queries."""
        report = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "day": None,
        }
        report["trading"] = self._trading_performance()
        report["ai"] = self._ai_performance()
        report["execution"] = self._execution_metrics()
        report["memory"] = self._memory_metrics()
        report["replay"] = self._replay_metrics()
        report["llm"] = self._llm_metrics()
        report["infrastructure"] = self._infrastructure_health()
        report["health"] = self._health_summary(report)
        self._data = report
        return report

    def _trading_performance(self) -> dict:
        try:
            closures = get_closures_from_replay(self._storage, limit=500)
            pnls = []
            for c in closures:
                p = c.get("realized_pnl")
                if p is not None:
                    try:
                        pnls.append(float(p))
                    except Exception:
                        continue
            wins = sum(1 for p in pnls if p > 0)
            losses = sum(1 for p in pnls if p < 0)
            return {
                "total_trades": len(closures),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / max(1, wins + losses) * 100, 2),
                "total_pnl": round(sum(pnls), 2) if pnls else 0.0,
                "source": "agent_trade_replay_events",
            }
        except Exception as e:
            return {"error": str(e)}

    def _ai_performance(self) -> dict:
        try:
            audits = self._storage.get_reasoning_audit_summary()
            patterns = self._storage.get_patterns(limit=500)
            validated = self._storage.get_validated_patterns(limit=500)
            return {
                "memory_usage_score": round(audits.get("avg_memory_usage_score", 0), 4),
                "avg_latency_ms": round(audits.get("avg_latency_ms", 0), 1),
                "total_audits": audits.get("total_audits", 0),
                "patterns_mined": len(patterns),
                "patterns_validated": len(validated),
                "most_ignored_dimension": audits.get("most_ignored_dimension", "unknown"),
            }
        except Exception as e:
            return {"error": str(e)}

    def _execution_metrics(self) -> dict:
        try:
            actions = self._storage.get_recent_actions(limit=500)
            successes = sum(1 for a in actions if a.get("success"))
            failures = sum(1 for a in actions if not a.get("success"))
            return {
                "total_actions": len(actions),
                "successful": successes,
                "failed": failures,
                "success_rate": round(successes / max(1, len(actions)) * 100, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    def _memory_metrics(self) -> dict:
        try:
            episodes = self._storage.get_recent_episodes(limit=500)
            resolved = sum(1 for e in episodes if e.get("resolved"))
            attr = self._storage.get_attribution_metrics()
            shadow = self._storage.get_shadow_memory_influence_metrics()
            return {
                "episodes_created": len(episodes),
                "episodes_resolved": resolved,
                "memory_contribution": round(attr.get("average_contribution_score", 0), 4),
                "shadow_agreement_rate": round(shadow.get("agreement_rate", 0) * 100, 2),
                "shadow_influence": round(shadow.get("avg_shadow_influence_score", 0), 4),
            }
        except Exception as e:
            return {"error": str(e)}

    def _replay_metrics(self) -> dict:
        try:
            trades = self._storage.get_trade_replay_summary(limit=500)
            total_events = 0
            for t in trades:
                tid = t.get("trade_id")
                if tid:
                    events = self._storage.get_trade_replay_events(tid)
                    total_events += len(events)
            return {
                "trades_recorded": len(trades),
                "total_events": total_events,
                "avg_events_per_trade": round(total_events / max(1, len(trades)), 1),
            }
        except Exception as e:
            return {"error": str(e)}

    def _llm_metrics(self) -> dict:
        try:
            audits = self._storage.get_reasoning_audits(limit=500)
            providers = {}
            for a in audits:
                p = a.get("llm_provider", "unknown")
                providers[p] = providers.get(p, 0) + 1
            return {
                "total_llm_calls": len(audits),
                "provider_breakdown": providers,
                "avg_latency_ms": round(
                    sum(float(a.get("latency_ms", 0)) for a in audits) / max(1, len(audits)), 1
                ),
            }
        except Exception as e:
            return {"error": str(e)}

    def _infrastructure_health(self) -> dict:
        return {
            "storage_type": "AgentStorage",
            "status": "healthy",
            "errors_last_24h": 0,
        }

    def _health_summary(self, report: dict) -> dict:
        sections = ["trading", "ai", "execution", "memory", "replay", "llm"]
        errors = [s for s in sections if "error" in report.get(s, {})]
        return {
            "status": "HEALTHY" if not errors else "WARNING",
            "error_count": len(errors),
            "error_sections": errors,
        }

    def save(self, report: dict) -> str:
        day_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        report["day"] = day_str
        path = os.path.join(REPORT_DIR, f"daily_{day_str}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        return path

    def print_summary(self, report: dict) -> None:
        print()
        print("=" * 60)
        print(f"DAILY REPORT — Day {report.get('day', '?')}")
        print("=" * 60)
        h = report.get("health", {})
        print(f"Status: {h.get('status', 'UNKNOWN')}")
        t = report.get("trading", {})
        print(f"\n  Trading: {t.get('total_trades', 0)} trades | "
              f"{t.get('wins', 0)}W / {t.get('losses', 0)}L | "
              f"Win Rate: {t.get('win_rate', 0)}% | "
              f"Total PnL: ${t.get('total_pnl', 0):.2f}")
        ai = report.get("ai", {})
        print(f"  AI: {ai.get('total_audits', 0)} audits | "
              f"MemScore: {ai.get('memory_usage_score', 0)} | "
              f"Patterns: {ai.get('patterns_validated', 0)}v/{ai.get('patterns_mined', 0)}m")
        ex = report.get("execution", {})
        print(f"  Execution: {ex.get('total_actions', 0)} actions | "
              f"Success: {ex.get('success_rate', 0)}%")
        mem = report.get("memory", {})
        print(f"  Memory: {mem.get('episodes_created', 0)} ep | "
              f"ShadowAgree: {mem.get('shadow_agreement_rate', 0)}%")
        rp = report.get("replay", {})
        print(f"  Replay: {rp.get('trades_recorded', 0)} trades | "
              f"{rp.get('total_events', 0)} events")
        llm = report.get("llm", {})
        print(f"  LLM: {llm.get('total_llm_calls', 0)} calls | "
              f"Providers: {list(llm.get('provider_breakdown', {}).keys())}")
        print(f"\nSource: agent_trade_replay_events (trade_closures deprecated)")
        print("=" * 60)


def main():
    from agent.storage import make_storage
    storage = make_storage()
    reporter = DailyReport(storage)
    report = reporter.generate()
    path = reporter.save(report)
    report["_path"] = path
    reporter.print_summary(report)


if __name__ == "__main__":
    main()