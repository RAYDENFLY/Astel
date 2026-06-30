"""
Phase 10.7A — 48-Hour Observation Mode: Hourly Monitor

Generates operational summaries every hour during observation mode.

Usage:
    # Start observation:
    python live_runner.py              # (runs AutonomousAgent in observe mode)

    # In another terminal, run hourly monitor:
    python -m agent.observe_hourly

    # This script runs in a loop, printing summaries every 3600 seconds.
    # Press Ctrl+C to stop monitoring (agent continues running).
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.storage import make_storage
from agent.daily_report import DailyReport

log = logging.getLogger("agent.observe_hourly")

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


class HourlyMonitor:
    """Generates operational summaries during observation mode."""

    def __init__(self, storage) -> None:
        self._storage = storage
        self._day = 0
        self._prev_plans = 0
        self._prev_episodes = 0
        self._prev_patterns = 0
        self._prev_audits = 0
        self._prev_actions = 0
        self._prev_trades = 0

    def generate_summary(self, hour: int) -> dict:
        """Generate an hourly operational summary."""
        now = datetime.now(tz=timezone.utc)

        # ── Agent Health ──
        try:
            plans = self._storage.get_recent_plans(limit=500)
            plans_count = len(plans)
        except Exception:
            plans_count = 0

        try:
            actions = self._storage.get_recent_actions(limit=500)
            actions_count = len(actions)
        except Exception:
            actions_count = 0

        try:
            audits = self._storage.get_reasoning_audits(limit=500)
            audits_count = len(audits)
        except Exception:
            audits_count = 0

        try:
            episodes = self._storage.get_recent_episodes(limit=500)
            episodes_count = len(episodes)
        except Exception:
            episodes_count = 0

        try:
            patterns = self._storage.get_patterns(limit=500)
            patterns_count = len(patterns)
        except Exception:
            patterns_count = 0

        try:
            trades = self._storage.get_trade_replay_summary(limit=500)
            trades_count = len(trades)
        except Exception:
            trades_count = 0

        # ── Compute deltas ──
        delta_plans = plans_count - self._prev_plans
        delta_episodes = episodes_count - self._prev_episodes
        delta_patterns = patterns_count - self._prev_patterns
        delta_audits = audits_count - self._prev_audits
        delta_actions = actions_count - self._prev_actions
        delta_trades = trades_count - self._prev_trades

        self._prev_plans = plans_count
        self._prev_episodes = episodes_count
        self._prev_patterns = patterns_count
        self._prev_audits = audits_count
        self._prev_actions = actions_count
        self._prev_trades = trades_count

        # ── Build report ──
        report = {
            "timestamp": now.isoformat(),
            "hour": hour,
            "agent": {
                "plans_total": plans_count,
                "plans_delta_1h": delta_plans,
                "actions_total": actions_count,
                "actions_delta_1h": delta_actions,
            },
            "llm": {
                "audits_total": audits_count,
                "audits_delta_1h": delta_audits,
            },
            "memory": {
                "episodes_total": episodes_count,
                "episodes_delta_1h": delta_episodes,
                "patterns_total": patterns_count,
                "patterns_delta_1h": delta_patterns,
            },
            "replay": {
                "trades_total": trades_count,
                "trades_delta_1h": delta_trades,
            },
            "health": "HEALTHY" if delta_actions >= 0 else "WARNING",
        }

        # ── Save to disk ──
        path = os.path.join(REPORT_DIR, f"hourly_{now.strftime('%Y-%m-%d_%H')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        return report

    def print_summary(self, report: dict) -> None:
        """Print hourly summary to stdout."""
        h = report["hour"]
        print()
        print(f"[Hour {h:2d}] {report['timestamp'][:19]}  Health: {report['health']}")
        print(f"  Plans:     {report['agent']['plans_total']:4d}  ({report['agent']['plans_delta_1h']:+d}/h)")
        print(f"  Actions:   {report['agent']['actions_total']:4d}  ({report['agent']['actions_delta_1h']:+d}/h)")
        print(f"  LLM Calls: {report['llm']['audits_total']:4d}  ({report['llm']['audits_delta_1h']:+d}/h)")
        print(f"  Episodes:  {report['memory']['episodes_total']:4d}  ({report['memory']['episodes_delta_1h']:+d}/h)")
        print(f"  Patterns:  {report['memory']['patterns_total']:4d}  ({report['memory']['patterns_delta_1h']:+d}/h)")
        print(f"  Trades:    {report['replay']['trades_total']:4d}  ({report['replay']['trades_delta_1h']:+d}/h)")


def main():
    """Run hourly monitoring loop."""
    storage = make_storage()
    monitor = HourlyMonitor(storage)

    hour = 0
    print("=" * 60)
    print("48-HOUR OBSERVATION MODE — HOURLY MONITOR")
    print("=" * 60)
    print("Monitoring AutonomousAgent in observe mode...")
    print("Press Ctrl+C to stop monitoring (agent continues).")
    print()

    try:
        while hour < 48:
            report = monitor.generate_summary(hour)
            monitor.print_summary(report)
            hour += 1
            if hour < 48:
                time.sleep(3600)  # Wait 1 hour
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")
    finally:
        # Print final summary
        print()
        print("=" * 60)
        print("OBSERVATION SUMMARY")
        print("=" * 60)

        # Generate a final daily report as well
        try:
            reporter = DailyReport(storage)
            final = reporter.generate()
            path = reporter.save(final)
            reporter.print_summary(final)
            print(f"\nFinal report saved: {path}")
        except Exception as e:
            print(f"Could not generate final report: {e}")

        print()
        print("To continue observing, run again:")
        print("  python -m agent.observe_hourly")
        print()
        print("To view the database directly:")
        print("  sqlite3 agent/agent.sqlite")
        print("  .tables")
        print()


if __name__ == "__main__":
    main()