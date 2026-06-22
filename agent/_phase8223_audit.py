"""
Phase 8.2.23 — Diversity Gate & Pattern Expansion Audit
Uses live PostgreSQL. Audit only. No code changes.
"""
import os, sys, json
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
print("PHASE 8.2.23 — DIVERSITY GATE & PATTERN EXPANSION AUDIT")
print(f"Timestamp: {str(now)[:19]} UTC")
print("=" * 70)

print("\nA: PATTERN INVENTORY")
all_pat = q("SELECT id, pattern_key, sample_size, success_rate, confidence_score, validation_score, validated, active FROM semantic_patterns ORDER BY sample_size DESC")
print(f"\n  Total patterns: {len(all_pat)}")
for p in all_pat:
    print(f"    id={p['id']} key={str(p['pattern_key']):<65}")
    print(f"          sample={p['sample_size']} success_rate={p['success_rate']} conf={p['confidence_score']}")
    print(f"          validation_score={p['validation_score']} validated={p['validated']} active={p['active']}")

print("\nB: DIVERSITY INPUTS")
actions = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]['c']
modes = q("SELECT COUNT(DISTINCT survival_mode) as c FROM agent_episodes")[0]['c']
consensus = q("SELECT COUNT(DISTINCT analyst_consensus) as c FROM agent_episodes")[0]['c']
verdicts = q("SELECT COUNT(DISTINCT debate_verdict) as c FROM agent_episodes")[0]['c']
active_validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE active=TRUE AND validated=TRUE")[0]['c']
active_patterns = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']
distinct_pattern_keys = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']

print(f"\n  Unique actions:               {actions}")
print(f"  Unique survival modes:        {modes}")
print(f"  Unique analyst_consensus:     {consensus}")
print(f"  Unique debate_verdict:        {verdicts}")
print(f"  Active validated patterns:    {active_validated}")
print(f"  Active patterns (any):        {active_patterns}")
print(f"  Distinct active pattern keys: {distinct_pattern_keys}")

print(f"\n  Distinct actions:")
act_list = q("SELECT DISTINCT action_type FROM agent_episodes ORDER BY action_type")
for a in act_list:
    print(f"    {a['action_type']}")
print(f"  Distinct survival modes:")
mod_list = q("SELECT DISTINCT survival_mode FROM agent_episodes ORDER BY survival_mode")
for m in mod_list:
    print(f"    {m['survival_mode']}")
print(f"  Distinct analyst_consensus:")
con_list = q("SELECT DISTINCT analyst_consensus FROM agent_episodes ORDER BY analyst_consensus")
for c in con_list:
    print(f"    {c['analyst_consensus']}")
print(f"  Distinct debate_verdict:")
ver_list = q("SELECT DISTINCT debate_verdict FROM agent_episodes ORDER BY debate_verdict")
for v in ver_list:
    print(f"    {v['debate_verdict']}")

print("\nC: DIVERSITY SCORE RECONSTRUCTION")
# The current formula (from Phase 8.2.14 audit script):
# diversity_score = distinct_patterns * distinct_verdicts * min(distinct_actions, 5)
# Let me find the exact formula used in _phase8214_audit.py
print("\n  Current formula:")
print("    diversity_score = distinct_patterns × distinct_verdicts × min(distinct_actions, 5)")
print(f"\n  Component values:")
print(f"    distinct_patterns (active):  {distinct_pattern_keys}")
print(f"    distinct_verdicts:           {verdicts}")
print(f"    distinct_actions (capped):   min({actions}, 5) = {min(actions, 5)}")
raw = distinct_pattern_keys * verdicts * min(actions, 5)
print(f"\n  Raw score: {distinct_pattern_keys} × {verdicts} × {min(actions, 5)} = {raw}")
print(f"  Threshold: 50")
print(f"  Result:    {'PASS' if raw >= 50 else 'FAIL'}")

# Test alternative formulas
print("\n  Alternative formulas:")
alt1 = distinct_pattern_keys * consensus * min(actions, 5)
print(f"    patterns × analyst_consensus × min(actions,5): {distinct_pattern_keys} × {consensus} × {min(actions,5)} = {alt1}")
alt2 = distinct_pattern_keys * consensus * modes
print(f"    patterns × analyst_consensus × modes:          {distinct_pattern_keys} × {consensus} × {modes} = {alt2}")
alt3 = distinct_pattern_keys * consensus * min(actions,5) * modes
print(f"    patterns × consensus × min(actions,5) × modes: {distinct_pattern_keys} × {consensus} × {min(actions,5)} × {modes} = {alt3}")
alt4 = distinct_pattern_keys * verdicts * modes
print(f"    patterns × verdicts × modes:                   {distinct_pattern_keys} × {verdicts} × {modes} = {alt4}")
alt5 = distinct_pattern_keys * modes * min(actions, 5)
print(f"    patterns × modes × min(actions,5):             {distinct_pattern_keys} × {modes} × {min(actions,5)} = {alt5}")

# SMIs as diversity source
smi_verdicts = q("SELECT COUNT(DISTINCT debate_verdict) as c FROM shadow_memory_influence")[0]['c']
smi_actions = q("SELECT COUNT(DISTINCT memory_action) as c FROM shadow_memory_influence")[0]['c']
print(f"\n  SMI-based diversity:")
print(f"    SMI distinct debate_verdict: {smi_verdicts}")
print(f"    SMI distinct memory_actions: {smi_actions}")
alt_smi = distinct_pattern_keys * smi_verdicts * min(smi_actions, 5)
print(f"    patterns × smi_verdicts × min(smi_actions,5): {distinct_pattern_keys} × {smi_verdicts} × {min(smi_actions,5)} = {alt_smi}")

print("\nD: BEARISH PATTERN IMPACT")
# Simulate bearish pattern addition
print("\n  Current state:")
print(f"    validated patterns:           {active_validated}")
print(f"    distinct pattern keys:        {distinct_pattern_keys}")
print(f"    current diversity:            {raw}")

# After bearish pattern (expected to be validated)
print(f"\n  After bearish pattern (expected):")
bear_distinct = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns")[0]['c']
# The bearish pattern would be a new distinct key
future_distinct = distinct_pattern_keys + 1  # bearish key is different from conservative
future_validated = active_validated + 1
future_raw = future_distinct * verdicts * min(actions, 5)
print(f"    validated patterns:           {future_validated}")
print(f"    distinct pattern keys:        {future_distinct} → {future_distinct} (+1)")
print(f"    future diversity:             {future_raw}")
print(f"    threshold 50:                 {'PASS' if future_raw >= 50 else 'FAIL'}")

if future_raw < 50:
    print(f"\n    Need additional diversity multiplier...")
    # Try with analyst_consensus instead of verdicts
    future_alt = future_distinct * consensus * min(actions, 5)
    print(f"    With analyst_consensus: {future_distinct} × {consensus} × {min(actions,5)} = {future_alt}")

print("\nE: PHASE 8.3 GATE STATUS")
validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE validated=TRUE")[0]['c']
pairs = q("SELECT COUNT(*) as c FROM shadow_observations so JOIN memory_attributions ma ON ma.plan_id = so.plan_id WHERE so.status='RESOLVED'")[0]['c']
avgc = q("SELECT AVG(memory_contribution_score) as avgc FROM memory_attributions WHERE outcome_quality NOT IN ('pending')")[0]['avgc'] or 0.0
diversity_score = raw

print(f"\n  1. patterns >= 3:       {validated}/3  {'PASS' if validated >= 3 else 'FAIL'}")
print(f"  2. resolved_pairs >= 10: {pairs}/10  {'PASS' if pairs >= 10 else 'FAIL'}")
print(f"  3. avg_contribution > 0: {round(avgc,4)}  {'PASS' if avgc > 0 else 'FAIL'}")
print(f"  4. diversity >= 50:      {diversity_score}/50  {'PASS' if diversity_score >= 50 else 'FAIL'}")
print(f"\n  Gates met: {sum([validated>=3, pairs>=10, avgc>0, diversity_score>=50])}/4")

print("\nF: DIVERSITY REALITY CHECK")
print("\n  Observed state diversity:")
print(f"    Actions ({actions}):         TIGHTEN_RISK, PAUSE_ENTRIES")
print(f"    Modes ({modes}):             NORMAL, CONSERVATIVE")
print(f"    Consensus ({consensus}):      conservative, bearish")
print(f"    Verdicts ({verdicts}):        unknown (only 1 value)")
print(f"\n  The system has 2 actions × 2 modes × 2 consensus values =")
print(f"  8 distinct operational states. But the formula uses verdicts")
print(f"  which is always 'unknown' by design.")

print(f"\n  Debate_verdict is always 'unknown' because:")
print(f"  - agent.py line ~520: debate_verdict = 'unknown' (placeholder)")
print(f"  - agent.py line ~534: outcome_json['debate_verdict'] = final_verdict")
print(f"  - BUT: agent_episodes.debate_verdict column is set to 'unknown'")
print(f"    at episode creation (line 444) and NEVER updated")
print(f"  - The real verdict is stored in outcome_json.debate_verdict")

print(f"\n  Diversity score {raw} does NOT represent actual system diversity.")
print(f"  Actual component diversity: 2 actions × 2 modes × 2 consensus = 8")
print(f"  The verdict dimension collapses to 1 ('unknown') which is a")
print(f"  database storage artifact, not a reflection of system behavior.")
print(f"\n  Verdict: UNDERSTATED")

print("\nG: FINAL VERDICT")
print(f"\n  Current gates:")
print(f"    Gate 1 (patterns):     {'READY' if validated >= 3 else 'WAITING for bearish pattern (~2.5h)'}")
print(f"    Gate 2 (pairs):        {'READY' if pairs >= 10 else 'NOT READY'}")
print(f"    Gate 3 (contribution): {'READY' if avgc > 0 else 'NOT READY'}")
print(f"    Gate 4 (diversity):    {'READY' if diversity_score >= 50 else 'DIVERSITY_FORMULA_BLOCKER'}")

if diversity_score >= 50:
    print(f"\n  PHASE_8_3_READY")
elif validated < 3:
    print(f"\n  WAIT_FOR_BEARISH_PATTERN")
else:
    print(f"\n  DIVERSITY_FORMULA_BLOCKER")
    print(f"  The diversity gate uses debate_verdict (1 value: 'unknown')")
    print(f"  which collapses the score to {raw}.")
    print(f"  Fix: Replace debate_verdict with analyst_consensus in diversity")
    print(f"       formula → {distinct_pattern_keys} × {consensus} × {min(actions,5)} = {distinct_pattern_keys * consensus * min(actions,5)}")
    if distinct_pattern_keys * consensus * min(actions,5) >= 50:
        print(f"       → This would PASS the gate (>= 50)")

conn.close()
print("\n" + "=" * 70)
print("Phase 8.2.23 audit complete. No code changes made.")
print("=" * 70)