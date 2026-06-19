# Phase 5 — Bull/Bear Researcher: Design Document

## Status
- **Phase 0-3:** Complete (Foundation → Observer → Shadow)
- **Phase 4:** Complete (TechnicalAnalyst, MarketAnalyst, SurvivalAnalyst)
- **Phase 4.5:** Complete (Consensus & Conflict Visualization)
- **Phase 5:** **Design Phase (this document)**

---

## 1. Architecture Overview

### Current Pipeline (Phase 4)

```
AgentSnapshot
    │
    ├─→ TechnicalAnalyst    (deterministic, no LLM)
    ├─→ MarketAnalyst       (deterministic, no LLM)
    ├─→ SurvivalAnalyst     (deterministic, no LLM)
    │
    └─→ AnalystTeam.summarize() → consensus verdict
            │
            └─→ Stored in analyst_reports table
```

### Proposed Pipeline (Phase 5)

```
AgentSnapshot
    │
    ├─→ TechnicalAnalyst
    ├─→ MarketAnalyst
    ├─→ SurvivalAnalyst
    │
    ├─→ Bull Researcher    ← NEW (LLM or deterministic)
    │       Output: BullCase {asset, thesis, catalysts, targets, confidence}
    │
    ├─→ Bear Researcher    ← NEW (LLM or deterministic)
    │       Output: BearCase {asset, thesis, risks, targets, confidence}
    │
    ├─→ Debate Engine      ← NEW
    │       Input: BullCase + BearCase + Technical + Market + Survival
    │       Output: Verdict {direction, conviction, reasoning}
    │
    └─→ Enhanced plan generation (consumes Debate verdict)
```

### Key Principle
Bull and Bear researchers run **independently** — neither sees the other's output until the Debate Engine. This prevents confirmation bias.

---

## 2. Component Definitions

### 2.1 Bull Researcher

| Attribute | Description |
|-----------|-------------|
| **Purpose** | Find reasons to be optimistic about each open position or the overall portfolio |
| **Trigger** | Every tick (if positions > 0), or on significant price movement |
| **Data Inputs** | `AgentSnapshot` + market prices from Dashboard API |
| **Output Schema** | See §3 |

**Bull case structure:**
```
For each position or overall market:
- What is going well? (upward trend, positive PnL, favorable entry)
- What catalysts exist? (support levels, oversold RSI, positive funding)
- What is the upside target? (nearest resistance, previous high)
- What is the confidence level? (0.0–1.0)
```

### 2.2 Bear Researcher

| Attribute | Description |
|-----------|-------------|
| **Purpose** | Find reasons to be pessimistic about each open position or the overall portfolio |
| **Trigger** | Same as Bull Researcher (paired) |
| **Data Inputs** | Same as Bull Researcher |
| **Output Schema** | See §3 |

**Bear case structure:**
```
For each position or overall market:
- What is going wrong? (downward trend, negative PnL, bad entry)
- What risks exist? (resistance levels, overbought RSI, negative funding)
- What is the downside target? (nearest support, previous low, liquidation)
- What is the confidence level? (0.0–1.0)
```

### 2.3 Debate Engine

| Attribute | Description |
|-----------|-------------|
| **Purpose** | Weight bull vs bear arguments, produce a final verdict |
| **Trigger** | After both Bull and Bear researchers have completed |
| **Data Inputs** | BullCase, BearCase, AnalystTeam consensus, current snapshot |
| **Output Schema** | See §3 |

**Debate logic:**
```
1. Receive BullCase and BearCase
2. Weight each by confidence
3. Factor in AnalystTeam consensus (safety override)
4. Produce final verdict:
   - direction: "long" | "short" | "flat" | "hedge"
   - conviction: 0.0–1.0
   - reasoning: combined summary
   - override: true if AnalystTeam consensus disagrees with debate
```

---

## 3. Output Schemas

### 3.1 BullCase (JSON stored in `bullbear_debates` table)

```json
{
  "researcher": "BullResearcher",
  "ts": "2026-06-18T10:00:00Z",
  "plan_id": 42,
  "overall_verdict": "bullish",
  "overall_confidence": 0.72,
  "asset_cases": [
    {
      "contract": "ADA_USDT",
      "verdict": "bullish",
      "confidence": 0.78,
      "reasons": [
        "RSI at 32 — oversold bounce likely",
        "Positive funding rate suggests long demand",
        "Price above 200 EMA on 4H"
      ],
      "upside_target": 0.42,
      "downside_risk": 0.32
    }
  ],
  "summary": "Position in ADA looks favorable for short-term bounce"
}
```

### 3.2 BearCase

```json
{
  "researcher": "BearResearcher",
  "ts": "2026-06-18T10:00:00Z",
  "plan_id": 42,
  "overall_verdict": "bearish",
  "overall_confidence": 0.55,
  "asset_cases": [
    {
      "contract": "ADA_USDT",
      "verdict": "bearish",
      "confidence": 0.55,
      "reasons": [
        "Volume declining — momentum weakening",
        "MACD bearish cross on 1H",
        "Open interest decreasing"
      ],
      "downside_target": 0.30,
      "upside_risk": 0.40
    }
  ],
  "summary": "ADA showing signs of weakening momentum"
}
```

### 3.3 Debate Verdict

```json
{
  "debate_id": 1,
  "ts": "2026-06-18T10:00:00Z",
  "plan_id": 42,
  "bull_verdict": "bullish",
  "bull_confidence": 0.72,
  "bear_verdict": "bearish",
  "bear_confidence": 0.55,
  "net_bias": "bullish",
  "net_conviction": 0.17,
  "debate_weight": 0.65,
  "analyst_consensus": "neutral",
  "analyst_confidence": 0.60,
  "final_verdict": "neutral",
  "final_conviction": 0.62,
  "override_by_analysts": false,
  "reasoning": "Bull case stronger (0.72 vs 0.55) but analyst consensus is neutral. Combined verdict: neutral with low conviction."
}
```

---

## 4. Database: `bullbear_debates` Table

### PostgreSQL Schema

```sql
CREATE TABLE IF NOT EXISTS bullbear_debates (
    id               SERIAL PRIMARY KEY,
    plan_id          INTEGER REFERENCES agent_plans(id),
    ts               TIMESTAMPTZ NOT NULL,
    bull_json        JSONB NOT NULL,
    bear_json        JSONB NOT NULL,
    verdict_json     JSONB NOT NULL,
    bull_confidence  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    bear_confidence  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    net_bias         TEXT NOT NULL DEFAULT 'neutral',
    final_verdict    TEXT NOT NULL DEFAULT 'neutral',
    final_conviction DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    override_flag    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_bullbear_ts ON bullbear_debates(ts DESC);
CREATE INDEX IF NOT EXISTS idx_bullbear_plan ON bullbear_debates(plan_id);
```

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS bullbear_debates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id          INTEGER REFERENCES agent_plans(id),
    ts              TEXT NOT NULL,
    bull_json       TEXT NOT NULL,
    bear_json       TEXT NOT NULL,
    verdict_json    TEXT NOT NULL,
    bull_confidence REAL NOT NULL DEFAULT 0.0,
    bear_confidence REAL NOT NULL DEFAULT 0.0,
    net_bias        TEXT NOT NULL DEFAULT 'neutral',
    final_verdict   TEXT NOT NULL DEFAULT 'neutral',
    final_conviction REAL NOT NULL DEFAULT 0.0,
    override_flag   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bullbear_ts ON bullbear_debates(ts DESC);
CREATE INDEX IF NOT EXISTS idx_bullbear_plan ON bullbear_debates(plan_id);
```

---

## 5. Storage Interface (to add to `AgentStorage`)

```python
@abstractmethod
def save_bullbear_debate(
    self,
    plan_id: int,
    ts: datetime,
    bull_json: str,
    bear_json: str,
    verdict_json: str,
    bull_confidence: float,
    bear_confidence: float,
    net_bias: str,
    final_verdict: str,
    final_conviction: float,
    override_flag: bool,
) -> int:
    """Returns debate_id."""
    ...

@abstractmethod
def get_recent_bullbear_debates(self, limit: int = 10) -> List[Dict[str, Any]]:
    ...
```

---

## 6. Dashboard API

| Endpoint | Method | Response |
|----------|--------|----------|
| `GET /api/agent/bullbear?limit=5` | GET | `{debates: [{id, plan_id, ts, bull, bear, verdict}]}` |
| `GET /api/agent/bullbear/latest` | GET | Single latest debate with full details |

---

## 7. Implementation Approaches

### Option A: Deterministic (Rule-Based)

**Approach:** No LLM calls. Purely mathematical.

**Bull scoring rules:**
- RSI < 30 → bullish signal (+0.2 confidence)
- Positive unrealized PnL → bullish (+0.1 per position)
- Win rate > 55% → bullish (+0.15)
- Drawdown < 2% → bullish (+0.1)

**Bear scoring rules:**
- RSI > 70 → bearish signal (+0.2)
- Negative unrealized PnL → bearish (+0.1 per position)
- Drawdown > 5% → bearish (+0.2)
- High leverage (> 5x) → bearish (+0.15)

**Pros/Cons:**

| Factor | Score |
|--------|-------|
| Cost | $0 (no API calls) |
| Speed | <1ms |
| Complexity | Low |
| Intelligence | Low — cannot understand market context |
| Token usage | 0 |
| Runtime impact | Negligible |

### Option B: Local LLM (Ollama)

**Approach:** Use `qwen2.5:7b` or `llama3.2:3b` locally.

**Prompt pattern:**
```
You are a Bull Researcher. Analyze the following trading snapshot and
build a bullish case for each open position. Be specific about catalysts.

[snapshot data]

Output JSON format: {asset_cases: [{contract, verdict, reasons, upside_target}]}
```

**Pros/Cons:**

| Factor | Score |
|--------|-------|
| Cost | $0 (local) |
| Speed | 2-10s per researcher (2-20s total) |
| Complexity | Medium |
| Intelligence | High — can reason about market context |
| Token usage | ~500-800 tokens per call |
| Runtime impact | Significant (blocks tick loop) |

### Option C: Groq (Cloud LLM)

**Approach:** Use `llama-3.3-70b-versatile` via Groq API.

**Prompt pattern:** Same as Option B, but faster inference.

**Pros/Cons:**

| Factor | Score |
|--------|-------|
| Cost | $0 (Groq free tier) |
| Speed | <1s per researcher |
| Complexity | Low (Groq already wired in LLMRouter) |
| Intelligence | Very high (70B model) |
| Token usage | ~500-800 tokens per call |
| Runtime impact | Low (~2s per tick) |
| Risk | Rate limits on free tier |

---

## 8. Cost & Performance Comparison

| Metric | Deterministic | Local LLM (7B) | Groq (70B) |
|--------|--------------|----------------|------------|
| **Cost per tick** | $0.00 | $0.00 | $0.00 (free tier) |
| **Tokens per tick** | 0 | ~1,200 (x2 researchers) | ~1,200 |
| **Latency per tick** | <1ms | 4-20s | 1-3s |
| **Monthly tokens (5-min ticks)** | 0 | ~10M tokens | ~10M tokens |
| **DeepSeek alternative cost** | $0 | ~$2.80/month | ~$2.80/month |
| **Implementation effort** | 1-2 days | 2-3 days | 1-2 days (reuse LLMRouter) |
| **Quality** | Low | Medium | High |
| **Blocking risk** | None | High (blocks tick) | Low |
| **Dependency** | None | Ollama running | Groq API key |

---

## 9. Recommendation: Hybrid MVP

### Phase 5 MVP Architecture

```
Researcher implementation: DETERMINISTIC (Option A)
Debate Engine: DETERMINISTIC (Option A)
LLM upgrade path: OPTIONAL — swap to Groq via config flag
```

### Rationale

1. **Zero cost — critical for "100 USDT survive or die"**
   - Can't risk cloud costs eating the treasury
   - Local LLM may not be available (user may not have Ollama)

2. **Deterministic is fast enough**
   - <1ms per tick → no impact on loop interval
   - Can run on EVERY tick, not just LLM intervals

3. **Deterministic rules can be improved iteratively**
   - Start simple, add more signals over time
   - Same pattern as existing TechnicalAnalyst/MarketAnalyst

4. **Groq upgrade path is trivial**
   - LLMRouter already supports Groq
   - Swap implementation when user enables `BULLBEAR_LLM_MODE=groq`

### Files to Create

| File | Description |
|------|-------------|
| `agent/researcher.py` | `BullResearcher`, `BearResearcher`, `DebateEngine` classes |
| `agent/storage.py` | Add `bullbear_debates` table + abstract methods + SQLite/PG impls |
| `agent/agent.py` | Run Bull/Bear researchers after analysts, store debates |
| `dashboard/app.py` | Add `GET /api/agent/bullbear` endpoint |
| `dashboard/templates/agent.html` | Add Bull/Bear panel |

### Timeline Estimate

| Phase | Duration |
|-------|----------|
| Deterministic implementation | 2-3 hours |
| Storage + integration | 1-2 hours |
| Dashboard API + UI | 1-2 hours |
| Testing + verification | 1 hour |
| **Total** | **5-8 hours** |

---

## 10. Open Questions

1. **Per-asset vs portfolio-level research?** — Portfolio-level is simpler for MVP. Per-asset can be added when positions > 1.

2. **Should Bull/Bear run every tick or only on LLM intervals?** — With deterministic implementation, every tick is fine (<1ms). With LLM, only on LLM intervals.

3. **Should the Debate Engine produce actions directly?** — No. Debate verdict feeds into the existing plan generation (rule-based + LLM). The planner still has final authority.

4. **How to handle override by analysts?** — If AnalystTeam consensus disagrees with debate verdict, the system should use the more conservative verdict (safety-first).

5. **Storage of reasoning for dashboard?** — Store full BullCase and BearCase JSONs. The dashboard can display reasons per researcher.

---

## 11. Next Steps

1. Approve this design document
2. Implement deterministic BullResearcher + BearResearcher
3. Implement DebateEngine
4. Add `bullbear_debates` table to storage
5. Integrate into agent tick (non-blocking)
6. Add dashboard API + UI
7. Verify with real data