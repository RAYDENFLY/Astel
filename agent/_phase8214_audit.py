"""
Phase 8.2.14 — First Resolved Pair Audit
Uses live PostgreSQL. No code changes. Audit only.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from collections import Counter
from datetime import datetime

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

def q(sql, params=None):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

print("=" * 70)
print("PHASE 8.2.14 — FIRST RESOLVED PAIR AUDIT")
print("=" * 70)

# =======================================================================
# A: PAIR RESOLUTION
# =======================================================================
print("\n" + "=" * 70)
print("A: PAIR RESOLUTION — Resolved Shadow-Attribution Pairs")
print("=" * 70)

# A resolved pair = a shadow_observation that is RESOLVED AND linked to a memory_attribution
# via shared plan_id, where the attribution has outcome_quality != 'unknown'/'pending'
# The linkage path: shadow_observation.plan_id -> agent_plans.id -> agent_episodes.plan_id? No.
# Actually: shadow_observation.plan_id = agent_episodes.plan_id? Let's check.
# shadow_observation has plan_id -> agent_plans(id)
# memory_attribution has plan_id and episode_id -> agent_episodes(id)
# But the pair is: shadow_evaluation (shadow_observation with status='RESOLVED')
# paired with memory_attribution via plan_id

# First, check the actual linkage: does shadow_observation reference agent_episodes?
# shadow_observation.plan_id -> agent_plans
# memory_attribution.plan_id -> agent_plans
# So pair = shadow_observation (RESOLVED) + memory_attribution on same plan_id

# Let's see what resolved shadow observations exist
print("\nResolved shadow observations:")
rows = q("""
    SELECT id, plan_id, ts, agreement, status, resolved_at,
           equity_24h_after, counterfactual_pnl
    FROM shadow_observations
    WHERE status = 'RESOLVED'
    ORDER BY ts
""")
print(f"  Total RESOLVED shadow observations: {len(rows)}")
for r in rows:
    print(f"  id={r['id']} plan={r['plan_id']} ts={str(r['ts'])[:19]} "
          f"agreement={r['agreement']} cf_pnl={r['counterfactual_pnl']}")

# Now find memory_attributions that share plan_ids with resolved shadow observations
print("\nResolved pairs (shadow_observation + memory_attribution on same plan_id):")
pairs = q("""
    SELECT so.id as shadow_id, so.plan_id, so.agreement, so.ts as shadow_ts,
           ma.id as attr_id, ma.outcome_quality, ma.memory_contribution_score,
           ma.debate_verdict, ma.ts as attr_ts
    FROM shadow_observations so
    JOIN memory_attributions ma ON ma.plan_id = so.plan_id
    WHERE so.status = 'RESOLVED'
    ORDER BY so.ts
""")
print(f"  Total resolved shadow-attribution pairs: {len(pairs)}")
for r in pairs:
    print(f"  shadow_id={r['shadow_id']} attr_id={r['attr_id']} "
          f"plan={r['plan_id']} shadow_agreement={r['agreement']} "
          f"outcome={r['outcome_quality']} contrib={r['memory_contribution_score']} "
          f"shadow_ts={str(r['shadow_ts'])[:19]}")

# Calculate total shadow observations
tot_shadow = q("SELECT COUNT(*) as c FROM shadow_observations")[0]['c']
resolved_shadow = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='RESOLVED'")[0]['c']
print(f"\n  Total shadow observations: {tot_shadow}")
print(f"  Resolved shadow observations: {resolved_shadow}")
print(f"  Pair coverage: {round(len(pairs)/max(1,tot_shadow)*100, 2)}% of total shadow obs")
print(f"  Pair coverage: {round(len(pairs)/max(1,resolved_shadow)*100, 2)}% of resolved shadow obs")

# First and latest pair timestamps
if pairs:
    first_ts = pairs[0]['shadow_ts']
    last_ts = pairs[-1]['shadow_ts']
    print(f"\n  First pair timestamp: {str(first_ts)[:19]}")
    print(f"  Latest pair timestamp: {str(last_ts)[:19]}")
else:
    print("\n  No resolved pairs found.")
    first_ts = None
    last_ts = None

# Total shadow evaluations (from shadow_memory_influence)
smi = q("SELECT COUNT(*) as c FROM shadow_memory_influence")[0]['c']
print(f"\n  Shadow memory influence evaluations: {smi}")

print("\nPAIR_STATUS:")
print(f"  total_resolved_pairs: {len(pairs)}")
print(f"  total_shadow_observations: {tot_shadow}")
print(f"  resolved_shadow_observations: {resolved_shadow}")
pair_coverage_pct = round(len(pairs)/max(1,tot_shadow)*100, 2) if tot_shadow > 0 else 0.0
print(f"  pair_coverage_pct: {pair_coverage_pct}%")
print(f"  first_pair_timestamp: {str(first_ts)[:19] if first_ts else 'N/A'}")
print(f"  latest_pair_timestamp: {str(last_ts)[:19] if last_ts else 'N/A'}")
print(f"  smi_evaluations: {smi}")

# =======================================================================
# B: BEARISH PATTERN ACTIVATION
# =======================================================================
print("\n" + "=" * 70)
print("B: BEARISH PATTERN ACTIVATION — TIGHTEN_RISK|CONSERVATIVE|bearish|unknown")
print("=" * 70)

pattern = q("SELECT * FROM semantic_patterns WHERE pattern_key = 'TIGHTEN_RISK|CONSERVATIVE|bearish|unknown'")
if pattern:
    p = pattern[0]
    print(f"\n  pattern_id: {p['id']}")
    print(f"  pattern_key: {p['pattern_key']}")
    print(f"  sample_size: {p['sample_size']}")
    print(f"  success_rate: {p['success_rate']}")
    print(f"  confidence_score: {p['confidence_score']}")
    print(f"  validation_score: {p['validation_score']}")
    print(f"  validated: {p['validated']}")
    print(f"  active: {p['active']}")
    print(f"  positive_count: {p['positive_count']}")
    print(f"  negative_count: {p['negative_count']}")
    print(f"  neutral_count: {p['neutral_count']}")
    print(f"  first_seen: {p['first_seen']}")
    print(f"  last_seen: {p['last_seen']}")
    print(f"  last_episode_id_processed: {p['last_episode_id_processed']}")
else:
    print("\n  Pattern NOT FOUND in semantic_patterns table.")
    # Look for similar patterns
    patterns = q("SELECT pattern_key, sample_size, confidence_score, validated, active FROM semantic_patterns ORDER BY sample_size DESC")
    print(f"\n  All patterns ({len(patterns)}):")
    for p in patterns:
        print(f"    {p['pattern_key']}: sample={p['sample_size']} conf={p['confidence_score']} validated={p['validated']} active={p['active']}")

# Check episodes matching the condition
print("\n  Episodes matching TIGHTEN_RISK/CONSERVATIVE/bearish:")
eps = q("""
    SELECT id, ts, action_type, survival_mode, analyst_consensus, debate_verdict,
           resolved, outcome_json::text as ojt
    FROM agent_episodes
    WHERE action_type = 'TIGHTEN_RISK'
      AND survival_mode = 'CONSERVATIVE'
      AND debate_verdict = 'bearish'
    ORDER BY ts
""")
print(f"  Total matching episodes: {len(eps)}")
for r in eps:
    dv_out = '?'
    try:
        o = json.loads(r['ojt']) if isinstance(r['ojt'], str) else r['ojt']
        dv_out = o.get('debate_verdict', 'N/A') if isinstance(o, dict) else 'N/A'
    except:
        dv_out = 'N/A'
    print(f"  ep={r['id']} ts={str(r['ts'])[:19]} resolved={r['resolved']} outcome_verdict={dv_out}")

# All episodes with CONSERVATIVE/bearish regardless of action
cons_bear = q("""
    SELECT action_type, COUNT(*) as c
    FROM agent_episodes
    WHERE survival_mode = 'CONSERVATIVE' AND debate_verdict = 'bearish'
    GROUP BY action_type
    ORDER BY c DESC
""")
print(f"\n  CONSERVATIVE/bearish by action_type:")
for r in cons_bear:
    print(f"    {r['action_type']}: {r['c']}")

print("\nBEARISH_PATTERN_STATUS:")
if pattern:
    p = pattern[0]
    print(f"  pattern_id: {p['id']}")
    print(f"  sample_size: {p['sample_size']}")
    print(f"  confidence_score: {p['confidence_score']}")
    print(f"  validation_score: {p['validation_score']}")
    print(f"  active: {bool(p['active'])}")
else:
    print(f"  pattern_id: NOT_FOUND")
    print(f"  sample_size: 0")
    print(f"  confidence_score: 0.0")
    print(f"  validation_score: 0.0")
    print(f"  active: false")

# =======================================================================
# C: CONTRIBUTION ANALYSIS
# =======================================================================
print("\n" + "=" * 70)
print("C: CONTRIBUTION ANALYSIS — Memory Contribution Scores")
print("=" * 70)

# All memory_attributions with non-pending outcome
all_attr = q("""
    SELECT id, episode_id, plan_id, memory_contribution_score, outcome_quality
    FROM memory_attributions
    WHERE outcome_quality NOT IN ('pending')
    ORDER BY memory_contribution_score
""")
print(f"\n  Total attributions (non-pending): {len(all_attr)}")

contrib_scores = [r['memory_contribution_score'] for r in all_attr if r['memory_contribution_score'] is not None]
if contrib_scores:
    avg_contrib = sum(contrib_scores) / len(contrib_scores)
    sorted_scores = sorted(contrib_scores)
    n = len(sorted_scores)
    if n % 2 == 0:
        median_contrib = (sorted_scores[n//2 - 1] + sorted_scores[n//2]) / 2
    else:
        median_contrib = sorted_scores[n//2]
    min_contrib = min(contrib_scores)
    max_contrib = max(contrib_scores)
    
    print(f"\n  Contribution distribution:")
    print(f"  Values: {[round(s, 4) for s in sorted_scores]}")
    
    print(f"\n  average_contribution: {round(avg_contrib, 4)}")
    print(f"  median_contribution: {round(median_contrib, 4)}")
    print(f"  min_contribution: {round(min_contrib, 4)}")
    print(f"  max_contribution: {round(max_contrib, 4)}")
    
    # Also by outcome_quality
    print(f"\n  By outcome quality:")
    for oq in ['positive', 'negative', 'neutral']:
        vals = [r['memory_contribution_score'] for r in all_attr if r['outcome_quality'] == oq and r['memory_contribution_score'] is not None]
        if vals:
            print(f"    {oq}: count={len(vals)} avg={round(sum(vals)/len(vals), 4)} min={round(min(vals), 4)} max={round(max(vals), 4)}")
else:
    print("  No contribution scores available.")
    avg_contrib = 0.0
    median_contrib = 0.0
    min_contrib = 0.0
    max_contrib = 0.0

print("\nCONTRIBUTION_STATUS:")
print(f"  average_contribution: {round(avg_contrib, 4)}")
print(f"  median_contribution: {round(median_contrib, 4)}")
print(f"  min_contribution: {round(min_contrib, 4)}")
print(f"  max_contribution: {round(max_contrib, 4)}")

# =======================================================================
# D: MEMORY RELIABILITY
# =======================================================================
print("\n" + "=" * 70)
print("D: MEMORY RELIABILITY — Memory Reliability Score")
print("=" * 70)

# Validated patterns
validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE validated=TRUE")[0]['c']
print(f"\n  Validated patterns: {validated}")

# Resolved pairs (from section A)
resolved_pairs = len(pairs)
print(f"  Resolved pairs: {resolved_pairs}")

# Average confidence across all memory_attributions
conf = q("SELECT AVG(memory_confidence) as avg_conf FROM memory_attributions WHERE outcome_quality NOT IN ('pending')")
avg_confidence = float(conf[0]['avg_conf']) if conf[0]['avg_conf'] is not None else 0.0
print(f"  Average confidence: {round(avg_confidence, 4)}")

# Disagreement rate
smi_metrics = q("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN agreement='DISAGREE' THEN 1 ELSE 0 END) as disagrees
    FROM shadow_memory_influence
""")[0]
total_smi = int(smi_metrics['total']) if smi_metrics['total'] else 0
disagrees = int(smi_metrics['disagrees']) if smi_metrics['disagrees'] else 0
disagreement_rate = round(disagrees / max(1, total_smi), 4) if total_smi > 0 else 0.0
print(f"  Shadow memory influence total: {total_smi}")
print(f"  Disagreements: {disagrees}")
print(f"  Disagreement rate: {disagreement_rate}")

# Also from memory_advice (which has its own agreement tracking)
adv_stats = q("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN difference_detected=TRUE THEN 1 ELSE 0 END) as diffs,
           AVG(confidence) as avg_conf
    FROM memory_advice
""")[0]
adv_total = int(adv_stats['total']) if adv_stats['total'] else 0
adv_diffs = int(adv_stats['diffs']) if adv_stats['diffs'] else 0
adv_agreement_rate = round((adv_total - adv_diffs) / max(1, adv_total), 4) if adv_total > 0 else 0.0
print(f"\n  Memory advice total: {adv_total}")
print(f"  Memory advice differences: {adv_diffs}")
print(f"  Memory advice agreement rate: {adv_agreement_rate}")

# Calculate MEMORY_RELIABILITY_SCORE
# Formula: (validated_patterns_weight * normalized_validated +
#            resolved_pairs_weight * normalized_pairs +
#            avg_confidence_weight +
#            agreement_rate_weight * (1 - disagreement_rate))
# Let's use a simple composite:
wc_validated = min(validated / 5.0, 1.0)  # target 5 validated patterns
wc_pairs = min(resolved_pairs / 10.0, 1.0)  # target 10 resolved pairs
wc_confidence = min(avg_confidence / 1.0, 1.0)  # target 1.0 confidence
wc_agreement = 1.0 - disagreement_rate  # higher agreement = better

memory_reliability_score = round(
    wc_validated * 0.25 +
    wc_pairs * 0.25 +
    wc_confidence * 0.25 +
    wc_agreement * 0.25,
    4
) * 100  # scale to 0-100

print(f"\n  MEMORY RELIABILITY COMPONENTS:")
print(f"    validated_patterns_weight: {round(wc_validated, 4)}")
print(f"    resolved_pairs_weight: {round(wc_pairs, 4)}")
print(f"    avg_confidence_weight: {round(wc_confidence, 4)}")
print(f"    agreement_weight (1-disagreement_rate): {round(wc_agreement, 4)}")

print(f"\nMEMORY_RELIABILITY_STATUS:")
print(f"  validated_patterns: {validated}")
print(f"  resolved_pairs: {resolved_pairs}")
print(f"  average_confidence: {round(avg_confidence, 4)}")
print(f"  disagreement_rate: {disagreement_rate}")
print(f"  memory_reliability_score: {memory_reliability_score} (scale 0-100)")

# =======================================================================
# E: PHASE 8.3 GATE
# =======================================================================
print("\n" + "=" * 70)
print("E: PHASE 8.3 GATE — Readiness Evaluation")
print("=" * 70)

# Gate criteria:
# 1. patterns >= 3
# 2. resolved pairs >= 10
# 3. avg contribution > 0
# 4. diversity score >= 50

total_patterns = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']
print(f"\n  1. Active patterns >= 3: {total_patterns} {'✓' if total_patterns >= 3 else '✗'}")
print(f"     (count: {total_patterns})")

print(f"  2. Resolved pairs >= 10: {resolved_pairs} {'✓' if resolved_pairs >= 10 else '✗'}")
print(f"     (count: {resolved_pairs})")

print(f"  3. Avg contribution > 0: {avg_contrib} {'✓' if avg_contrib > 0 else '✗'}")
print(f"     (value: {round(avg_contrib, 4)})")

# Diversity score: count distinct pattern_keys * distinct outcome_qualities * distinct actions
distinct_patterns = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']
distinct_actions = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]['c']
distinct_modes = q("SELECT COUNT(DISTINCT survival_mode) as c FROM agent_episodes")[0]['c']
distinct_verdicts = q("SELECT COUNT(DISTINCT debate_verdict) as c FROM agent_episodes")[0]['c']
diversity_score = distinct_patterns * distinct_verdicts * min(distinct_actions, 5)
print(f"\n  4. Diversity score >= 50: {diversity_score} {'✓' if diversity_score >= 50 else '✗'}")
print(f"     distinct_patterns: {distinct_patterns}")
print(f"     distinct_actions: {distinct_actions}")
print(f"     distinct_modes: {distinct_modes}")
print(f"     distinct_verdicts: {distinct_verdicts}")
print(f"     diversity_score (patterns*verdicts*min(actions,5)): {diversity_score}")

gates_met = sum([
    total_patterns >= 3,
    resolved_pairs >= 10,
    avg_contrib > 0,
    diversity_score >= 50
])

print(f"\n  Gates met: {gates_met}/4")
print(f"  Phase 8.3 Gate: {'PASSED' if gates_met == 4 else 'NOT YET READY'}")

print("\nPHASE_8_3_READY:")
print(f"  patterns_met: {total_patterns >= 3} ({total_patterns}/3)")
print(f"  resolved_pairs_met: {resolved_pairs >= 10} ({resolved_pairs}/10)")
print(f"  avg_contribution_met: {avg_contrib > 0} ({round(avg_contrib, 4)})")
print(f"  diversity_met: {diversity_score >= 50} ({diversity_score}/50)")
print(f"  gates_passed: {gates_met}/4")

# =======================================================================
# F: VERDICT
# =======================================================================
print("\n" + "=" * 70)
print("F: VERDICT")
print("=" * 70)

if gates_met == 4:
    print("\n  READY_FOR_PHASE_8_3")
    print(f"  All {gates_met}/4 Phase 8.3 gates satisfied.")
    print(f"  Active patterns: {total_patterns} (>=3: yes)")
    print(f"  Resolved pairs: {resolved_pairs} (>=10: yes)")
    print(f"  Avg contribution: {round(avg_contrib, 4)} (>0: yes)")
    print(f"  Diversity score: {diversity_score} (>=50: yes)")
else:
    print("\n  CONTINUE_COLLECTION")
    print(f"  Only {gates_met}/4 Phase 8.3 gates satisfied.")
    print(f"  Missing gates:")
    if total_patterns < 3:
        print(f"    - patterns: need {3 - total_patterns} more (current: {total_patterns})")
    if resolved_pairs < 10:
        print(f"    - resolved pairs: need {10 - resolved_pairs} more (current: {resolved_pairs})")
    if avg_contrib <= 0:
        print(f"    - avg contribution needs to be > 0 (current: {round(avg_contrib, 4)})")
    if diversity_score < 50:
        print(f"    - diversity score: need {50 - diversity_score} more (current: {diversity_score})")

conn.close()
print("\n" + "=" * 70)
print("Audit complete. No code changes made.")
print("=" * 70)