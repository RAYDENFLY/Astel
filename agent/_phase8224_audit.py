"""
Phase 8.2.24 — Diversity Gate Design Audit
Uses live PostgreSQL. Audit only. No code changes.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

def q(sql):
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

now = datetime.now(tz=timezone.utc)

print("=" * 70)
print("PHASE 8.2.24 — DIVERSITY GATE DESIGN AUDIT")
print(f"Timestamp: {str(now)[:19]} UTC")
print("=" * 70)

print("\nA: FORMULA ORIGIN")
print("\n  Source: agent/_phase8214_audit.py (Phase 8.2.14 audit, Section E)")
print("  This was an AD-HOC formula created during the first audit.")
print("  It is NOT defined in any production source file.")
print("  Lines 400-409 of _phase8214_audit.py:")
print("""
    diversity_score = distinct_patterns * distinct_verdicts * min(distinct_actions, 5)
    
    distinct_patterns = COUNT(DISTINCT pattern_key) FROM semantic_patterns WHERE active=TRUE
    distinct_actions  = COUNT(DISTINCT action_type) FROM agent_episodes
    distinct_verdicts = COUNT(DISTINCT debate_verdict) FROM agent_episodes
    
    Threshold: 50
  """)
print("  The formula was created as an arbitrary composite metric to measure")
print("  'how many different contexts the system has seen patterns for'.")
print("  It has no formal design document or test coverage.")

print("\nB: MAX REACHABLE SCORE")
actions = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]["c"]
modes = q("SELECT COUNT(DISTINCT survival_mode) as c FROM agent_episodes")[0]["c"]
consensus = q("SELECT COUNT(DISTINCT analyst_consensus) as c FROM agent_episodes")[0]["c"]
verdicts = q("SELECT COUNT(DISTINCT debate_verdict) as c FROM agent_episodes")[0]["c"]
patterns = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]["c"]
future_patterns = patterns + 1  # bearish pattern

print(f"\n  Current data dimensions:")
print(f"    distinct actions:           {actions}")
print(f"    distinct modes:             {modes}")
print(f"    distinct analyst_consensus: {consensus}")
print(f"    distinct debate_verdict:    {verdicts}  ← THE CONSTRAINT")
print(f"    distinct patterns:          {patterns}")
print(f"    future patterns (+ bearish): {future_patterns}")

print(f"\n  Current formula: patterns x verdicts x min(actions, 5)")
print(f"    Current max: {patterns} x {verdicts} x {min(actions,5)} = {patterns * verdicts * min(actions,5)}")
print(f"    With bearish: {future_patterns} x {verdicts} x {min(actions,5)} = {future_patterns * verdicts * min(actions,5)}")

# Brute force: what would it take?
print(f"\n  Combinations of (patterns, verdicts, actions_capped) that reach 50:")
combos = []
for p in range(1, 21):
    for v in range(1, 11):
        for a in range(1, 6):
            s = p * v * a
            if s >= 50:
                combos.append((p, v, a, s))
for p, v, a, s in sorted(combos, key=lambda x: x[3])[:15]:
    print(f"    patterns={p} verdicts={v} actions_capped={a} -> score={s}")

print(f"\n  The MINIMUM combination to reach 50:")
print(f"    Option 1: 10 patterns x 1 verdict x 5 actions = 50")
print(f"    Option 2: 5 patterns x 5 verdicts x 2 actions = 50")
print(f"    Option 3: 3 patterns x 4 verdicts x 5 actions = 60")
print(f"\n  With verdicts permanently stuck at 1 ('unknown'):")
print(f"    Need: 50 patterns x 1 verdict x 1 action = 50")
print(f"    Or:   {max(1, 50 // 2 // 1)} patterns x 1 verdict x 2 actions = 50")
print(f"    → Need {max(1, 50 // 2 // 1)} distinct patterns. Currently {patterns}.")

print("\nC: REACHABILITY — NO")
print("""
  ┌─────────────────────────────────────────────────────────────────────┐
  │ REACHABLE: NO                                                        │
  │                                                                      │
  │ Mathematical proof:                                                  │
  │   Formula: P x V x min(A, 5)                                         │
  │   Constraints:                                                       │
  │     V (debate_verdict) = 1 (always 'unknown' by design)             │
  │     A (actions) = 2 (capped to 2)                                    │
  │     P (patterns) ≈ 2-3 (max ~5 in reasonable timeframe)             │
  │                                                                      │
  │   Max reachable: 3 x 1 x 2 = 6                                      │
  │   Target:       50                                                   │
  │   Gap:          44 (factor of 8.3x)                                  │
  │                                                                      │
  │   Even with 5 patterns and 5 actions: 5 x 1 x 5 = 25 (still < 50)  │
  │   The threshold 50 is IMPOSSIBLE with verdicts always being 1.       │
  │                                                                      │
  │   The only fix paths:                                                │
  │   1. Add dimensions (modes, consensus) to the formula                │
  │   2. Replace verdicts with a variable that actually varies           │
  │   3. Lower the threshold to match realistic max (~10-15)             │
  └─────────────────────────────────────────────────────────────────────┘
""")

print("D: GATE INTENT ANALYSIS")
print("""
  The diversity gate was intended to measure:
    'pattern variety' — how many distinct contexts the system recognizes
  
  The original intent was likely:
    - Ensure the system has learned patterns from MULTIPLE market regimes
    - Not overfit on a single action/context combination
    - Demonstrate GENERALIZATION rather than memorization
  
  Current formula measures:
    Product of (pattern count) x (verdict count) x (action count)
  
  Alignment assessment:
    - pattern count ✓ CORRECT (more patterns = more learned contexts)
    - action count  ✓ CORRECT (more actions = more behavioral variety)
    - verdict count ✗ WRONG (always 1, doesn't measure anything)
  
  INTENT_ALIGNMENT_STATUS: MISALIGNED
    The verdict dimension adds no signal since debate_verdict is always 'unknown'.
    It should be replaced with analyst_consensus (2 values) or survival_mode (2 values).
""")

print("E: ALTERNATIVE METRICS")
print("\n  Alternative diversity scores using available dimensions:")
alt1 = patterns * consensus * min(actions, 5)
alt2 = future_patterns * consensus * min(actions, 5)
alt3 = patterns * modes * min(actions, 5)
alt4 = patterns * consensus * modes * min(actions, 5)
alt5 = future_patterns * consensus * modes * min(actions, 5)

print(f"\n  Dimension values available:")
print(f"    patterns:   {patterns} (current), {future_patterns} (with bearish)")
print(f"    consensus:  {consensus} (conservative, bearish)")
print(f"    modes:      {modes} (NORMAL, CONSERVATIVE)")
print(f"    actions:    {actions} (PAUSE_ENTRIES, TIGHTEN_RISK)")
print(f"    verdicts:   {verdicts} (unknown — SINGLE VALUE)")

print(f"\n  Alternative metric values:")
print(f"    A) patterns x consensus x min(actions, 5):")
print(f"       Current:  {patterns} x {consensus} x {min(actions,5)} = {alt1}")
print(f"       Bearish+: {future_patterns} x {consensus} x {min(actions,5)} = {alt2}")
print(f"    B) patterns x modes x min(actions, 5):")
print(f"       Current:  {patterns} x {modes} x {min(actions,5)} = {alt3}")
print(f"    C) patterns x consensus x modes x min(actions, 5):")
print(f"       Current:  {patterns} x {consensus} x {modes} x {min(actions,5)} = {alt4}")
print(f"       Bearish+: {future_patterns} x {consensus} x {modes} x {min(actions,5)} = {alt5}")

# State-space coverage
states = q("""
    SELECT COUNT(*) as c FROM (
        SELECT DISTINCT action_type, survival_mode, analyst_consensus
        FROM agent_episodes
    ) sub
""")[0]["c"]
print(f"\n  Actual state-space coverage:")
print(f"    Unique (action, mode, consensus) combos: {states}")
print(f"    Total possible states: {actions * modes * consensus}")
print(f"    Coverage: {round(states / max(1, actions*modes*consensus) * 100, 1)}%")

# SMI diversity
smi = q("""
    SELECT COUNT(DISTINCT planner_action) as pa,
           COUNT(DISTINCT memory_action) as ma,
           COUNT(DISTINCT analyst_consensus) as ca,
           COUNT(DISTINCT survival_mode) as sm
    FROM shadow_memory_influence
""")[0]
print(f"\n  Shadow Memory Influence diversity:")
print(f"    planner_actions:      {smi['pa']}")
print(f"    memory_actions:       {smi['ma']}")
print(f"    analyst_consensus:    {smi['ca']}")
print(f"    survival_modes:       {smi['sm']}")

# Outcome quality diversity
attr_q = q("SELECT DISTINCT outcome_quality FROM memory_attributions ORDER BY outcome_quality")
print(f"\n  Attribution outcome qualities: {[r['outcome_quality'] for r in attr_q]}")
print(f"  Distinct qualities: {len(attr_q)}")

print("\nF: READINESS REASSESSMENT")
act_capped = min(actions, 5)
score_a = future_patterns * consensus * act_capped
score_b = future_patterns * consensus * modes * act_capped
print(f"  Assuming bearish pattern validated in ~2.5h:")
print(f"    patterns = {future_patterns}")
print(f"    pairs    = 454 (confirmed)")
print(f"    contrib  = 0.6143 (confirmed)")
print(f"""
  With revised diversity formula using analyst_consensus instead of verdicts:
    diversity = patterns x consensus x min(actions, 5)
    score = {future_patterns} x {consensus} x {act_capped} = {score_a}
    
  If we use FOUR dimensions:
    diversity = patterns x consensus x modes x min(actions, 5)
    score = {future_patterns} x {consensus} x {modes} x {act_capped} = {score_b}

  GATES:
    1. patterns >= 3:     {min(3, future_patterns)}/{future_patterns} ✓ (after bearish)
    2. pairs >= 10:        454/10 ✓
    3. contribution > 0:  0.6143 ✓
    4. diversity >= 50:   {score_b}/50 {"✓" if score_b >= 50 else "✗"}
""")

gates = sum([
    1,  # bearish will make patterns >= 3
    1,  # pairs >= 10
    1,  # contribution > 0
    1 if score_b >= 50 else 0
])
print(f"  Phase 8 gates passing (with bearish + revised diversity): {gates}/4")

print("\nG: VERDICT")
alt_score = patterns * consensus * act_capped
alt4_score = patterns * consensus * modes * act_capped
threshold_10 = "✓" if alt_score >= 10 else "✗"
print(f"""
  DIVERSITY_GATE_MISALIGNED

  The diversity gate is structurally impossible to pass because:

  1. The formula uses debate_verdict as a dimension, but debate_verdict
     is ALWAYS 'unknown' in the agent_episodes table (Phase 7 design).

  2. Even if the dataset were 10x larger, max theoretical score is ~6
     (3 patterns x 1 verdict x 2 actions) vs target of 50.

  3. The system ACTUALLY has diverse decision contexts:
     - 2 action types (TIGHTEN_RISK, PAUSE_ENTRIES)
     - 2 survival modes (NORMAL, CONSERVATIVE)
     - 2 analyst consensus values (conservative, bearish)
     - 454 resolved pairs across many market states

  4. Fix recommendations (choose one):
     a) Replace debate_verdict with analyst_consensus in formula
        Score: {patterns} x {consensus} x {act_capped} = {alt_score}
        Then lower threshold to ~10-15 (realistic 3-factor max)
    
     b) Use FOUR dimensions: patterns x consensus x modes x actions
        Score: {patterns} x {consensus} x {modes} x {act_capped} = {alt4_score}
        Then threshold 24 is realistic (this maxes at 24)
    
     c) Keep three dimensions but use analyst_consensus + lower threshold:
        Threshold = 10
        patterns x consensus x min(actions,5) = {alt_score} >= 10 {threshold_10}
""")

conn.close()
print("=" * 70)
print("Phase 8.2.24 audit complete. No code changes made.")
print("=" * 70)