"""
Phase 11.0 — Decision Pipeline Trace

Instruments every stage of the AutonomousAgent decision pipeline so
every tick explains exactly WHY a trade was or was not executed.

Each stage records:
  - timestamp
  - duration_ms
  - status (SUCCESS / FAILED / SKIPPED / BLOCKED)
  - human-readable reason
  - stage-specific data

Stages tracked:
  1. Market Snapshot
  2. Analyst Team
  3. Consensus
  4. ML Prediction
  5. Memory Context
  6. LLM Reasoning
  7. AgentPlan
  8. Guardrails
  9. Risk Validation
  10. ExecutionEngine
  11. Exchange Response

The trace is stored in memory and can be persisted to the database
for historical analysis.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.storage import AgentStorage

log = logging.getLogger("agent.pipeline_trace")


class PipelineStage(str):
    """Names of decision pipeline stages."""
    SNAPSHOT = "market_snapshot"
    ANALYST = "analyst_team"
    CONSENSUS = "consensus"
    ML = "ml_prediction"
    MEMORY = "memory_context"
    LLM = "llm_reasoning"
    PLAN = "agent_plan"
    GUARDRAIL = "guardrails"
    RISK = "risk_validation"
    EXECUTION = "execution_engine"
    EXCHANGE = "exchange_response"


class StageStatus(str):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


@dataclass
class StageRecord:
    """Record of a single decision pipeline stage."""
    stage: str
    status: str
    reason: str = ""
    duration_ms: float = 0.0
    timestamp: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(tz=timezone.utc).isoformat()


@dataclass
class PipelineTrace:
    """
    Complete decision pipeline trace for one agent tick.
    
    Stores every stage that ran and captures the exact point where
    execution stopped.
    """
    tick_number: int = 0
    plan_id: int = 0
    trade_id: str = ""
    timestamp: str = ""
    stages: List[StageRecord] = field(default_factory=list)
    stopped_at_stage: str = ""
    stopped_at_reason: str = ""
    final_status: str = "PENDING"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(tz=timezone.utc).isoformat()

    def add_stage(
        self,
        stage: str,
        status: str,
        reason: str = "",
        duration_ms: float = 0.0,
        data: Optional[Dict[str, Any]] = None,
    ) -> StageRecord:
        """Record a stage and return it."""
        record = StageRecord(
            stage=stage,
            status=status,
            reason=reason,
            duration_ms=round(duration_ms, 1),
            data=data or {},
        )
        self.stages.append(record)
        return record

    def stop(self, stage: str, reason: str) -> None:
        """Mark that the pipeline stopped at this stage."""
        self.stopped_at_stage = stage
        self.stopped_at_reason = reason
        self.final_status = "BLOCKED"

    def succeed(self) -> None:
        """Mark pipeline as completed successfully."""
        self.final_status = "COMPLETED"

    def fail(self, reason: str) -> None:
        """Mark pipeline as failed."""
        self.final_status = "FAILED"
        self.stopped_at_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trace to dictionary."""
        return {
            "tick_number": self.tick_number,
            "plan_id": self.plan_id,
            "trade_id": self.trade_id,
            "timestamp": self.timestamp,
            "final_status": self.final_status,
            "stopped_at_stage": self.stopped_at_stage,
            "stopped_at_reason": self.stopped_at_reason,
            "stages": [asdict(s) for s in self.stages],
        }


class DecisionPipelineTracer:
    """
    Tracks decision pipeline traces for every agent tick.
    
    Maintains the latest trace in memory and persists completed traces
    to the database for historical analysis.
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage
        self._current: Optional[PipelineTrace] = None
        self._history: List[PipelineTrace] = []
        self._max_history = 100

    # ── Lifecycle ──

    def begin_tick(self, tick_number: int) -> PipelineTrace:
        """Start trace for a new agent tick."""
        self._current = PipelineTrace(tick_number=tick_number)
        return self._current

    def current(self) -> Optional[PipelineTrace]:
        """Get the current tick's trace."""
        return self._current

    def finish_tick(self) -> None:
        """Complete the current tick's trace and persist."""
        if self._current is None:
            return
        # Auto-detect stopped stage from stage statuses
        if not self._current.stopped_at_stage and self._current.stages:
            # Find the last stage that is BLOCKED or FAILED
            for stage in reversed(self._current.stages):
                if stage.status in (StageStatus.BLOCKED, StageStatus.FAILED):
                    self._current.stop(stage.stage, stage.reason)
                    break
            else:
                # All stages are SUCCESS or SKIPPED → pipeline completed
                self._current.succeed()
        # Persist
        self._persist(self._current)
        # Add to history
        self._history.append(self._current)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self._current = None

    def cancel_tick(self, reason: str) -> None:
        """Cancel current tick (e.g., treasury dead)."""
        if self._current is None:
            return
        self._current.fail(reason)
        self._persist(self._current)
        self._history.append(self._current)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self._current = None

    # ── Stage shortcuts ──

    def snapshot(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.SNAPSHOT, status, reason, duration_ms, data)

    def analyst(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.ANALYST, status, reason, duration_ms, data)

    def consensus(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.CONSENSUS, status, reason, duration_ms, data)

    def ml(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.ML, status, reason, duration_ms, data)

    def memory(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.MEMORY, status, reason, duration_ms, data)

    def llm(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.LLM, status, reason, duration_ms, data)

    def plan(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.PLAN, status, reason, duration_ms, data)

    def guardrail(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.GUARDRAIL, status, reason, duration_ms, data)

    def risk(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.RISK, status, reason, duration_ms, data)

    def execution(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.EXECUTION, status, reason, duration_ms, data)

    def exchange(self, status: str, reason: str = "", duration_ms: float = 0.0, data: Optional[Dict] = None) -> None:
        self._add_stage(PipelineStage.EXCHANGE, status, reason, duration_ms, data)

    # ── Query ──

    def get_latest(self) -> Optional[PipelineTrace]:
        """Return the most recent complete trace."""
        if self._history:
            return self._history[-1]
        return self._current

    def get_history(self, limit: int = 20) -> List[PipelineTrace]:
        """Return recent traces in reverse chronological order."""
        return list(reversed(self._history[-limit:]))

    def get_by_tick(self, tick_number: int) -> Optional[PipelineTrace]:
        """Find trace by tick number."""
        for t in reversed(self._history):
            if t.tick_number == tick_number:
                return t
        return None

    # ── Internal ──

    def _add_stage(self, stage: str, status: str, reason: str, duration_ms: float, data: Optional[Dict]) -> None:
        if self._current is None:
            return
        self._current.add_stage(stage, status, reason, duration_ms, data)

    def _persist(self, trace: PipelineTrace) -> None:
        """Persist trace to database."""
        try:
            trace_dict = trace.to_dict()
            # Store in a simple JSON-based record (no schema change needed)
            # Use the agent_trade_replay_events table with a virtual event type
            self._storage.save_trade_replay_event(
                trade_id=f"pipeline_{trace.tick_number}_{int(time.time())}",
                event_type="pipeline_trace",
                event_data=json.dumps(trace_dict),
                event_index=0,
                status=trace.final_status,
            )
        except Exception as e:
            log.warning("Pipeline trace persistence failed (non-fatal): %s", e)