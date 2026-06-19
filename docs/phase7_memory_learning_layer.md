# Phase 7 — Memory & Learning Layer

## Implementation Plan (No Code)

---

## 1. Architecture Audit Summary

### Current Data Flow

```
Snapshot → Analyst Team → Consensus → Bull Researcher → Bear Researcher
    → Debate Engine → Plan Generator (Rule + LLM) → Guardrails → Execution
    → Shadow Observer → Experiment Tracking
```

### What's Missing

| Gap | Impact | Evidence |
|-----|--------|----------|
| No outcome feedback loop | Agent repeats mistakes | Shadow observations stored but never consumed |
| No pattern recognition | Same conditions → same decisions, even if previous failed | Analyst/Bull/Bear reports are written, never queried |
| No strategy evolution | Rule-based + LLM prompt are static | `policy.py` thresholds hard-coded, LLM prompt has no historical context |
| No survival learning | Cannot answer "what worked when treasury was low?" | `experiment_runs` tracks score but doesn't inform decisions |
| No memory retrieval | Each tick is a "first day" for the agent | `_tick()` processes snapshot in isolation |

### Current Memory-Adjacent Data (Already Stored)

| Table | What It Stores | Memory Potential |
|-------|---------------|------------------|
| `shadow_observations` | Agreement, equity_change_24h, counterfactual_pnl | **HIGH** — tells us if agent recommendations were correct |
| `analyst_reports` | Per-analyst verdicts, confidence, reasons | **MEDIUM** — which analysts are reliable in which conditions |
| `bullbear_debates` | Bull/bear verdicts, net bias, final verdict | **MEDIUM** — which research bias correlates with survival |
| `experiment_runs` | Survival score, drawdown, capital path | **HIGH** — full experiment trajectory for learning |
| `agent_actions` | Action results (success/fail, detail) | **HIGH** — which actions work in which modes |
| `agent_treasury` | Treasury history with survival mode | **HIGH** — capital evolution context |
| `agent_plans` | Full plan + input snapshot | **HIGH** — complete decision context |

---

## 2. Memory Integration Points

### Point A: After Action Execution (Immediate)
**Where:** `agent.py` → `_tick()` → after `execute_action()` returns result  
**What to record:**
- Action type, params, success/failure
- Snapshot context (DD, exposure, treasury, survival mode)
- Result detail (blocked reason, error, trade outcome)
- Timestamp + plan_id reference

### Point B: After Shadow Resolution (24h delayed)
**Where:** `agent.py` → `_tick()` → after `self._shadow.resolve_pending()`  
**What to record:**
- Was the agent's recommendation correct? (AGREE vs DISAGREE)
- Equity change 24h after decision
- Counterfactual PnL (if available)
- Condition context at time of recommendation

### Point C: After Survival Mode Change (Event-Based)
**Where:** `agent.py` → `_tick()` → after `determine_survival_mode()` changes mode  
**What to record:**
- What triggered the mode change (DD, exposure, errors, treasury)
- Was the mode change effective? (did conditions improve within N ticks?)
- Duration spent in each mode

### Point D: After Experiment Tracking Update (Per Tick)
**Where:** `agent.py` → `_tick()` → at end of experiment tracking block  
**What to record:**
- Survival score trajectory
- Capital growth/decline per tick
- Action → outcome pairs for reinforcement learning

---

## 3. Memory System Design

### 3.1 Three-Tier Memory Architecture

```
┌─────────────────────────────────────────────────┐
│                 Episodic Memory                  │
│  "What happened" — timestamped events with      │
│  full context (snapshot + action + outcome)      │
├─────────────────────────────────────────────────┤
│                 Semantic Memory                  │
│  "What works" — aggregated patterns extracted   │
│  from episodic memory (conditions → best action) │
├─────────────────────────────────────────────────┤
│               Procedural Memory                  │
│  "How to decide" — learned policy rules that    │
│  override / augment rule-based + LLM planning    │
└─────────────────────────────────────────────────┘
```

### 3.2 Episodic Memory Schema

```sql
CREATE TABLE agent_episodes (
    id              SERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL,
    
    -- Context (input snapshot summary)
    survival_mode   TEXT NOT NULL,
    equity          DOUBLE PRECISION,
    treasury_usdt   DOUBLE PRECISION,
    drawdown_pct    DOUBLE PRECISION,
    exposure_x      DOUBLE PRECISION,
    open_positions  INTEGER,
    win_rate_30d    DOUBLE PRECISION,
    runway_days     DOUBLE PRECISION,
    
    -- Decision
    plan_id         INTEGER REFERENCES agent_plans(id),
    action_type     TEXT,
    action_params   JSONB,
    action_why      TEXT,
    
    -- Research context
    analyst_consensus   TEXT,
    bull_verdict        TEXT,
    bear_verdict        TEXT,
    debate_verdict      TEXT,
    
    -- Immediate outcome
    action_success      BOOLEAN,
    guardrail_blocked   BOOLEAN,
    guardrail_reason    TEXT,
    
    -- Delayed outcome (filled by shadow resolution)
    shadow_obs_id       INTEGER REFERENCES shadow_observations(id),
    equity_change_24h   DOUBLE PRECISION,
    agreement           TEXT,           -- AGREE / DISAGREE
    
    -- Survival impact
    survival_delta      DOUBLE PRECISION,  -- treasury change after this action
    survival_score_at   DOUBLE PRECISION,
    
    -- Memory metadata
    importance_score    DOUBLE PRECISION DEFAULT 0.5,   -- computed weight
    decay_factor        DOUBLE PRECISION DEFAULT 1.0,   -- multiplied by age
    is_locked           BOOLEAN DEFAULT FALSE            -- prevent decay
);

-- Indexes for fast retrieval
CREATE INDEX idx_episodes_ts ON agent_episodes(ts DESC);
CREATE INDEX idx_episodes_mode ON agent_episodes(survival_mode, drawdown_pct, exposure_x);
CREATE INDEX idx_episodes_action ON agent_episodes(action_type, action_success);
CREATE INDEX idx_episodes_importance ON agent_episodes(importance_score DESC);
```

### 3.3 Semantic Memory Schema (Derived Patterns)

```sql
CREATE TABLE agent_patterns (
    id              SERIAL PRIMARY KEY,
    last_updated    TIMESTAMPTZ NOT NULL,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    
    -- Context bucket (discretized conditions)
    survival_mode   TEXT NOT NULL,
    drawdown_bucket TEXT NOT NULL,      -- 'low' (<3%), 'mid' (3-8%), 'high' (8-15%), 'critical' (>15%)
    exposure_bucket TEXT NOT NULL,       -- 'low' (<2x), 'moderate' (2-4x), 'high' (4-6x), 'extreme' (>6x)
    treasury_bucket TEXT NOT NULL,       -- 'healthy' (>$20), 'low' ($10-20), 'critical' ($5-10), 'depleted' (<$5)
    
    -- What worked
    recommended_action  TEXT NOT NULL,
    success_rate        DOUBLE PRECISION,    -- fraction of times this action succeeded
    avg_equity_change   DOUBLE PRECISION,    -- avg 24h equity change when using this action
    risk_adjusted_score DOUBLE PRECISION,    -- success_rate / stddev(equity_change)
    
    -- Statistics
    total_attempts  INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    failure_count   INTEGER NOT NULL DEFAULT 0,
    
    UNIQUE(survival_mode, drawdown_bucket, exposure_bucket, treasury_bucket, recommended_action)
);
```

### 3.4 Procedural Memory Schema (Learned Rules)

```sql
CREATE TABLE agent_rules (
    id              SERIAL PRIMARY KEY,
    created_ts      TIMESTAMPTZ NOT NULL,
    last_triggered  TIMESTAMPTZ,
    trigger_count   INTEGER NOT NULL DEFAULT 0,
    
    -- Rule condition (applied when all conditions match)
    condition_mode      TEXT,               -- NORMAL / CONSERVATIVE / DEFENSIVE / HIBERNATE / ANY
    condition_dd_min    DOUBLE PRECISION,   -- drawdown >= this (NULL = no limit)
    condition_dd_max    DOUBLE PRECISION,   -- drawdown < this (NULL = no limit)
    condition_treasury_min DOUBLE PRECISION,
    condition_treasury_max DOUBLE PRECISION,
    condition_exposure_min  DOUBLE PRECISION,
    condition_exposure_max  DOUBLE PRECISION,
    condition_win_rate_min  DOUBLE PRECISION,
    
    -- Rule action
    recommended_action  TEXT NOT NULL,
    action_params_json  JSONB,
    
    -- Effectiveness
    effectiveness_score DOUBLE PRECISION DEFAULT 0.5,
    applied_count       INTEGER NOT NULL DEFAULT 0,
    success_count       INTEGER NOT NULL DEFAULT 0,
    
    -- Metadata
    source              TEXT NOT NULL DEFAULT 'pattern_mining',  -- 'pattern_mining', 'manual', 'llm_derived'
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);
```

### 3.5 Memory Scoring Algorithm

Each episode gets an `importance_score` (0.0 - 1.0) computed from:

```
importance_score = w1 * survival_impact + w2 * novelty + w3 * recency + w4 * confidence

Where:
  survival_impact = |treasury_change| / initial_treasury  (capped at 0.5)
  novelty         = inverse frequency of similar episodes
  recency         = 1.0 - (hours_ago / max_age_hours)  (decay over 30 days)
  confidence      = agreement_rate_at_time (from shadow) OR 0.5 if unknown

  w1 = 0.40  (survival impact matters most)
  w2 = 0.25  (novel patterns get attention)
  w3 = 0.20  (recent events more relevant)
  w4 = 0.15  (confidence in the outcome)
```

### 3.6 Memory Decay Strategy

**Goal:** Old, irrelevant memories fade out; critical memories persist.

```
decay_factor = exp(-λ * days_since_event)

Where:
  λ = 0.05 for normal events (half-life ≈ 14 days)
  λ = 0.01 for locked events (half-life ≈ 69 days)
  λ = 0.10 for low-importance events (half-life ≈ 7 days)
  
An episode is "archived" (not deleted, but excluded from retrieval) when:
  importance_score * decay_factor < 0.1
```

**Locking mechanism:**
- Episodes with `importance_score > 0.8` are auto-locked
- Episodes involving treasury near-death (< $5) are auto-locked
- Episodes where a new best survival score was achieved are auto-locked

---

## 4. Memory Retrieval System

### 4.1 Retrieval Triggers

Memory is retrieved at three key points in the agent loop:

| Trigger Point | What to Retrieve | How to Use |
|--------------|------------------|------------|
| Before rule-based plan generation | Past actions in similar conditions | Override/supplement rule-based actions |
| Before LLM plan generation | Top 5 most relevant episodes | Inject as context into LLM prompt |
| Before guardrail check | Past outcomes of this action type | Adjust guardrail strictness |

### 4.2 Similarity Matching

Retrieve episodes where current context is similar:

```
def find_similar_episodes(current_snapshot, top_k=5):
    """
    Similarity criteria (weighted):
    - survival_mode EXACT match: weight 30%
    - drawdown_pct within ±25%: weight 25%
    - exposure_x within ±1.0x: weight 20%
    - treasury within ±50%: weight 15%
    - win_rate_30d within ±10%: weight 10%
    
    Returns top_k episodes sorted by weighted similarity.
    Episodes with importance_score * decay_factor < 0.1 are excluded.
    """
```

### 4.3 Pattern Extraction (Semantic Memory Mining)

Run periodically (every 50 ticks OR on demand):

```
def mine_patterns():
    """
    1. Group episodes by (survival_mode, drawdown_bucket, exposure_bucket, treasury_bucket)
    2. For each group, compute success_rate per action_type
    3. Update agent_patterns table
    4. If a pattern has success_rate > 0.7 AND count > 5:
       - Derive agent_rules entry with condition matching the bucket
       - Set effectiveness_score = success_rate * avg_equity_change_weight
    5. If a pattern has success_rate < 0.3 AND count > 3:
       - Derive negative rule (avoid this action in these conditions)
       - Set effectiveness_score = (1 - success_rate)
    """
```

### 4.4 LLM Context Injection

When calling the LLM for plan generation, inject relevant memories:

```
def build_llm_context(snapshot):
    similar = find_similar_episodes(snapshot, top_k=5)
    patterns = get_patterns_for_current_conditions(snapshot)
    
    prompt_context = f"""
    [MEMORY: Past experiences in similar conditions]
    {format_episodes_for_prompt(similar)}
    
    [MEMORY: What has worked in these conditions]
    {format_patterns_for_prompt(patterns)}
    """
    
    return SYSTEM_PROMPT + prompt_context + snapshot.to_prompt_text()
```

---

## 5. Dashboard Visibility

### 5.1 New API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/agent/memory/stats` | Memory system health (total episodes, avg score, patterns found, rules active) |
| `GET /api/agent/memory/patterns` | Derived patterns grouped by condition bucket |
| `GET /api/agent/memory/rules` | Active learned rules with effectiveness |
| `GET /api/agent/memory/timeline` | Episodic memory timeline with importance scores |
| `GET /api/agent/memory/replay?episode_id=X` | Full replay of a specific episode (snapshot → decision → outcome) |
| `GET /api/agent/learning/curve` | Learning curve: survival score vs episodes processed |

### 5.2 Dashboard UI Components

**Memory Panel (new tab in Research Console):**
1. **Memory Health Card** — Total episodes, avg importance, decay rate, pattern count
2. **Pattern Table** — Condition buckets → best action → success rate → attempts
3. **Rule List** — Active learned rules with toggle (enable/disable)
4. **Memory Timeline** — Scatter plot of episodes (x=time, y=importance_score, color=action_success)
5. **Learning Curve** — Survival score vs cumulative episodes (is the agent learning?)
6. **Episode Replay Modal** — Click an episode to see: snapshot context → action taken → outcome → 24h result
7. **Pattern Effectiveness Gauge** — For current conditions, show what past patterns suggest

### 5.3 Key KPIs for Dashboard

```
Memory KPIs:
- Memory Efficiency = patterns_generated / episodes_stored
- Rule Accuracy = successful_rule_applications / total_rule_applications
- Learning Rate = Δsurvival_score / Δepisodes (over last 100 episodes)
- Memory Utilization = memory_injected_plans / total_plans
```

---

## 6. Storage Requirements

### 6.1 New Tables (Both PostgreSQL and SQLite)

| Table | Est. Row Size | Est. Growth/Day | Purpose |
|-------|--------------|-----------------|---------|
| `agent_episodes` | ~500 bytes | ~1,440 rows (5min intervals) = ~720 KB/day | Full decision history |
| `agent_patterns` | ~200 bytes | ~10-50 rows (per mining run) | Derived patterns |
| `agent_rules` | ~300 bytes | ~1-5 rows (rarely created) | Learned procedural rules |
| `memory_metrics_log` | ~100 bytes | ~288 rows (5min) = ~28 KB/day | Memory performance tracking |

### 6.2 Storage Budget

```
Daily storage increase: ~750 KB/day (episodes + metrics)
Monthly storage increase: ~22 MB/month
With PostgreSQL compression: ~15 MB/month
For 1 year of operation: ~180 MB (negligible for modern systems)
```

### 6.3 Archive Strategy

- Episodes older than 90 days: move to `agent_episodes_archive` (same schema, separate table)
- Patterns older than 180 days: recompute from archive + active episodes
- Rules are never auto-deleted (only deactivated by effectiveness_score < 0.1)

---

## 7. Experiment Interaction

### 7.1 Memory-Augmented Experiments

When running experiments with `AGENT_INITIAL_TREASURY_USDT=100`:

1. **Experiment A (Control):** No memory — current behavior
2. **Experiment B (Memory):** Full memory system active
3. **Metric:** Does memory improve survival time? Survival score at 30 days?

### 7.2 Experiment Variables

The following should be configurable per experiment:

```
MEMORY_ENABLED=true|false              — master switch
MEMORY_RETRIEVAL_K=5                   — number of episodes to retrieve
MEMORY_IMPORTANCE_W1=0.40              — survival impact weight
MEMORY_IMPORTANCE_W2=0.25              — novelty weight
MEMORY_IMPORTANCE_W3=0.20              — recency weight
MEMORY_IMPORTANCE_W4=0.15              — confidence weight
MEMORY_DECAY_LAMBDA=0.05               — decay rate
MEMORY_PATTERN_MIN_SAMPLES=5           — min episodes to form a pattern
MEMORY_PATTERN_MIN_SUCCESS_RATE=0.7    — min success rate to create a rule
MEMORY_LLM_CONTEXT_ENABLED=true|false  — inject memories into LLM prompt
MEMORY_GUARDRAIL_ADAPTIVE=true|false   — adjust guardrails based on memory
```

### 7.3 Measuring Memory Impact

```
Key metrics to compare between control and memory experiments:
1. Days to treasury depletion (longer = better)
2. Peak survival score achieved
3. Number of "dangerous" actions avoided
4. LLM cost savings (fewer calls due to rule-based override)
5. Decision consistency (less variance in similar conditions)
6. Recovery speed after drawdown events
```

### 7.4 Experiment overrides

The experiment tracking system needs a new field:

```sql
ALTER TABLE experiment_runs ADD COLUMN memory_config JSONB;
-- Stores the MEMORY_* config that was active during this experiment
```

---

## 8. Integration Architecture

### 8.1 New Module: `agent/memory.py`

```
agent/memory.py
├── MemorySystem (main orchestrator)
│   ├── record_episode()          — Point A + C: store after action/survival change
│   ├── resolve_episode()         — Point B: update with 24h outcome
│   ├── retrieve()                — find similar episodes for current context
│   ├── get_patterns()            — get mined patterns for conditions
│   ├── get_rules()               — get active learned rules for override
│   ├── mine_patterns()           — periodic pattern extraction
│   └── get_stats()               — dashboard KPIs
├── EpisodicMemory
│   ├── store()                   — insert into agent_episodes
│   ├── find_similar()            — similarity matching
│   ├── compute_importance()      — scoring algorithm
│   └── apply_decay()             — update decay_factor for all episodes
├── SemanticMemory
│   ├── mine()                    — group episodes → compute success rates
│   ├── get_for_conditions()      — retrieve patterns matching current context
│   └── update()                  — upsert agent_patterns
├── ProceduralMemory
│   ├── derive_rules()            — create rules from high-confidence patterns
│   ├── evaluate_rules()          — test rules against new episodes
│   └── deactivate_rules()        — disable low-effectiveness rules
└── MemoryUtils
    ├── bucket_conditions()       — discretize continuous values
    ├── compute_similarity()      — weighted similarity score
    └── format_for_prompt()       — format episodes for LLM injection
```

### 8.2 Integration Points in Agent Loop

The following pseudo-code shows where memory hooks go in `agent.py` `_tick()`:

```python
def _tick(self):
    # ... existing code unchanged ...
    
    # === NEW: Initialize memory system ===
    if self._memory is None:
        self._memory = MemorySystem(self._storage)
    
    # ... snapshot fetch, analyst, survival mode (unchanged) ...
    
    # 5. Rule-based plan (unchanged)
    rule_plan = generate_rule_based_plan(snapshot, self._policy_cfg)
    
    # === NEW: Memory-augmented rule plan ===
    # Check if memory suggests better actions for current conditions
    memory_rules = self._memory.get_rules(snapshot)
    if memory_rules and rule_plan is None:
        # Memory suggests an action even when rule-based plan doesn't
        rule_plan = self._memory.build_memory_plan(snapshot, memory_rules)
    elif memory_rules and rule_plan:
        # Override/modify rule plan with high-confidence memory rules
        rule_plan = self._memory.merge_with_rules(rule_plan, memory_rules)
    
    # 6. LLM plan (memory-augmented context)
    should_call_llm = self._should_call_llm(snapshot)
    if should_call_llm:
        # === NEW: Inject memory context into LLM prompt ===
        memory_context = self._memory.build_llm_context(snapshot)
        # (LLM prompt now includes "what worked in similar situations")
        llm_plan, usage = self._llm.generate_plan(snapshot, memory_context=memory_context)
        # ...
    
    # ... action execution loop (unchanged) ...
    
    # === NEW: Record episode after each action ===
    for action in filtered_plan.proposed_actions:
        # ... guardrail check, execute (unchanged) ...
        
        # Record episode
        self._memory.record_episode(
            snapshot=snapshot,
            plan_id=plan_id,
            action=action,
            success=success,
            result=result,
            guardrail_blocked=not allowed,
            guardrail_reason=reason if not allowed else None,
        )
    
    # ... shadow observation, analyst save, bull/bear save (unchanged) ...
    
    # === NEW: Resolve episodes from shadow observations ===
    resolved = self._shadow.resolve_pending()
    if resolved > 0:
        self._memory.resolve_pending_episodes()
    
    # === NEW: Periodic pattern mining (every 50 ticks) ===
    if self._loop_count % 50 == 0:
        self._memory.mine_patterns()
    
    # ... experiment tracking (unchanged) ...
    
    # === NEW: Log memory metrics to experiment ===
    memory_stats = self._memory.get_stats()
    # Attach to experiment_run.notes or new field
```

### 8.3 Storage Changes

**AgentStorage** needs new abstract methods:

```python
class AgentStorage(ABC):
    # Existing methods (unchanged) ...
    
    # ── Memory ─────────────────────────────────────────────────
    @abstractmethod
    def save_episode(self, episode: Dict[str, Any]) -> int: ...
    
    @abstractmethod
    def update_episode(self, episode_id: int, updates: Dict[str, Any]) -> None: ...
    
    @abstractmethod
    def find_similar_episodes(self, context: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    def get_episodes_by_age(self, max_days: int) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    def save_pattern(self, pattern: Dict[str, Any]) -> None: ...
    
    @abstractmethod
    def get_patterns(self, context: Dict[str, Any]) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    def save_rule(self, rule: Dict[str, Any]) -> int: ...
    
    @abstractmethod
    def get_active_rules(self, context: Dict[str, Any]) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    def update_rule_effectiveness(self, rule_id: int, success: bool) -> None: ...
    
    @abstractmethod
    def get_memory_stats(self) -> Dict[str, Any]: ...
    
    @abstractmethod
    def apply_decay(self, lambda_factor: float) -> int: ...
    # Returns count of episodes archived
```

---

## 9. Implementation Sequence

### Phase 7A (Core Memory — 1-2 days)

| Step | File | What to Build |
|------|------|---------------|
| 1 | `agent/storage.py` | Add abstract methods + PostgreSQL/SQLite implementations for memory tables |
| 2 | `sql` (PG schema) | Add `agent_episodes`, `agent_patterns`, `agent_rules` tables |
| 3 | `agent/memory.py` | `MemorySystem` class with `record_episode()`, `retrieve()`, `get_stats()` |
| 4 | `agent/agent.py` | Integrate `record_episode()` after action execution (Point A) |
| 5 | `dashboard/app.py` | Add `/api/agent/memory/stats` endpoint |
| 6 | `dashboard/templates/agent.html` | Add Memory Health card |

### Phase 7B (Shadow Resolution + Learning — 2-3 days)

| Step | File | What to Build |
|------|------|---------------|
| 7 | `agent/memory.py` | `resolve_pending_episodes()` — hook into shadow resolution (Point B) |
| 8 | `agent/memory.py` | `compute_importance()` — scoring algorithm |
| 9 | `agent/memory.py` | `apply_decay()` — decay routine |
| 10 | `agent/agent.py` | Call `resolve_pending_episodes()` after shadow resolve |
| 11 | `agent/memory.py` | `mine_patterns()` — pattern extraction algorithm |
| 12 | `agent/agent.py` | Periodic `mine_patterns()` call (every 50 ticks) |
| 13 | `dashboard/app.py` | `/api/agent/memory/patterns`, `/api/agent/memory/timeline` |

### Phase 7C (Actionable Memory — 2-3 days)

| Step | File | What to Build |
|------|------|---------------|
| 14 | `agent/memory.py` | `derive_rules()` — convert patterns to procedural rules |
| 15 | `agent/memory.py` | `get_rules()` — retrieve rules matching current conditions |
| 16 | `agent/memory.py` | `build_memory_plan()` — create plan from memory rules |
| 17 | `agent/agent.py` | Integrate memory rules into plan generation |
| 18 | `agent/memory.py` | `build_llm_context()` — format memories for LLM prompt |
| 19 | `agent/llm_client.py` | Accept optional `memory_context` parameter |
| 20 | `agent/agent.py` | Pass memory context to LLM when generating plan |

### Phase 7D (Dashboard + Experiment — 1-2 days)

| Step | File | What to Build |
|------|------|---------------|
| 21 | `dashboard/app.py` | `/api/agent/learning/curve`, `/api/agent/memory/replay` |
| 22 | `dashboard/templates/agent.html` | Full Memory panel UI |
| 23 | `agent/storage.py` | Add `memory_config` to `experiment_runs` |
| 24 | `agent/agent.py` | Log memory config to experiment tracking |
| 25 | `agent/schema.py` | Add `MemoryConfig` pydantic model |
| 26 | `agent/memory.py` | `get_stats()` for full dashboard visibility |

---

## 10. Edge Cases & Risks

| Risk | Mitigation |
|------|-----------|
| Memory table grows too fast | Implement archive strategy at 90 days; periodic cleanup |
| Memory retrieval slows down agent loop | Limit `find_similar_episodes()` to top_k=5; use indexed queries; consider caching frequently retrieved patterns |
| False patterns from sparse data | Minimum sample threshold (=5) before deriving rules; effectiveness score decays quickly if not confirmed |
| LLM prompt becomes too long with memory context | Limit to top 3 episodes + summary; truncate to max 2000 chars |
| Memory conflicts with survival mode | Always let deterministic survival mode override memory suggestions (policy.py still wins) |
| Cold start (no memories yet) | Graceful: if `find_similar_episodes()` returns 0, behavior is unchanged from current |
| Pattern mining runs too frequently | Run every 50 ticks (≈ 4 hours at 5-min intervals) |
| Decay makes everything irrelevant | Lock important episodes (near-death events, new best scores) to prevent decay |

---

## 11. Success Criteria

The Phase 7 implementation is complete when:

1. ✅ Every action execution creates a memory episode
2. ✅ Shadow resolution updates episodes with 24h outcomes
3. ✅ Importance scoring + decay work correctly
4. ✅ Similarity retrieval returns relevant episodes within 100ms
5. ✅ Pattern mining extracts meaningful rules from organized episodes
6. ✅ Memory rules can influence/replace rule-based plans
7. ✅ LLM planning includes historical context from memory
8. ✅ Dashboard shows all memory KPIs
9. ✅ Experiment tracking incorporates memory configuration
10. ✅ Memory system can be toggled off for A/B testing

---

## 12. Backward Compatibility

- All existing tables remain unchanged
- New columns on `experiment_runs` are nullable (no migration needed for existing experiments)
- Memory system defaults to disabled (requires `MEMORY_ENABLED=true` env var or config)
- When disabled, agent behavior is identical to current
- All new API endpoints return `{"enabled": false}` when memory is off