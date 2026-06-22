"""
Phase 8.2.19 — Shadow Resolution Recovery Audit
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
print("PHASE 8.2.19 — SHADOW RESOLUTION RECOVERY AUDIT")
print(f"Timestamp: {str(now)[:19]} UTC")
print("=" * 70)

print("\n" + "=" * 70)
print("A: SHADOW RECOVERY")
print("=" * 70)

rows = q("SELECT status, COUNT(*) as cnt FROM shadow_observations GROUP BY status ORDER BY cnt DESC")
total = sum(r['cnt'] for r in rows)
print(f"\n  BEFORE (Phase 8.2.15):  PENDING_24H=535  RESOLVED=0")
for r in rows:
    print(f"  {r['status']}: {r['cnt']}")
resolved = sum(r['cnt'] for r in rows if r['status'] == 'RESOLVED')
print(f"  TOTAL: {total}")
print(f"  resolution_rate_pct: {round(resolved/max(1,total)*100, 2)}%")
print(f"  CHANGE: resolved increased by {resolved} (was 0)")

print("\n" + "=" * 70)
print("B: PAIR RECOVERY")
print("=" * 70)

pairs = q("""
    SELECT so.id as shadow_id, so.plan_id, so.agreement, so.ts as shadow_ts,
           ma.id as attr_id, ma.outcome_quality, ma.memory_contribution_score
    FROM shadow_observations so
    JOIN memory_attributions ma ON ma.plan_id = so.plan_id
    WHERE so.status = 'RESOLVED'
    ORDER BY so.ts
""")
print(f"\n  BEFORE (Phase 8.2.14):  0 resolved pairs")
print(f"  AFTER:  {len(pairs)} resolved shadow-attribution pairs")

for r in pairs:
    ts = str(r['shadow_ts'])[:19] if r['shadow_ts'] else 'N/A'
    print(f"  shadow_id={r['shadow_id']} plan={r['plan_id']} attr_id={r['attr_id']} "
          f"outcome={r['outcome_quality']} contrib={r['memory_contribution_score']} ts={ts}")

tot_obs = q("SELECT COUNT(*) as c FROM shadow_observations")[0]['c']
print(f"\n  pair_coverage_pct: {round(len(pairs)/max(1,tot_obs)*100, 2)}%")

if pairs:
    print(f"  first_pair_timestamp: {str(pairs[0]['shadow_ts'])[:19]}")
    print(f"  latest_pair_timestamp: {str(pairs[-1]['shadow_ts'])[:19]}")
else:
    print(f"  first_pair_timestamp: N/A")
    print(f"  latest_pair_timestamp: N/A")

print("\n" + "=" * 70)
print("C: THROUGHPUT")
print("=" * 70)

# Resolved in last 5 min
r5 = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL AND EXTRACT(EPOCH FROM (NOW() - resolved_at)) < 300")[0]['c']
print(f"\n  resolved in last 5 minutes: {r5}")

# Resolved in last hour
r1h = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL AND EXTRACT(EPOCH FROM (NOW() - resolved_at)) < 3600")[0]['c']
print(f"  resolved in last hour: {r1h}")

# Still eligible but pending
old_p = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='PENDING_24H' AND EXTRACT(EPOCH FROM (NOW() - ts)) > 86400")[0]['c']
print(f"  observations >24h old but still PENDING_24H: {old_p}")

# Young pending
young_p = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='PENDING_24H' AND EXTRACT(EPOCH FROM (NOW() - ts)) <= 86400")[0]['c']
print(f"  observations <=24h old (not yet eligible): {young_p}")

# Check resolved_at dates (first and last resolved)
resolved_time = q("SELECT MIN(resolved_at) as first_res, MAX(resolved_at) as last_res FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL")
if resolved_time and resolved_time[0]['first_res']:
    print(f"\n  first resolution timestamp: {str(resolved_time[0]['first_res'])[:19]}")
    print(f"  latest resolution timestamp: {str(resolved_time[0]['last_res'])[:19]}")
    delta = resolved_time[0]['last_res'] - resolved_time[0]['first_res']
    print(f"  resolution window: {delta.total_seconds():.0f}s")
else:
    print(f"\n  no resolved observations found")

print("\n" + "=" * 70)
print("D: BEARISH PATTERN STATUS — TIGHTEN_RISK|CONSERVATIVE|bearish|unknown")
print("=" * 70)

bearish_pat = q("SELECT * FROM semantic_patterns WHERE pattern_key = 'TIGHTEN_RISK|CONSERVATIVE|bearish|unknown'")
if bearish_pat:
    p = bearish_pat[0]
    print(f"\n  exists:          True")
    print(f"  pattern_id:      {p['id']}")
    print(f"  sample_size:     {p['sample_size']}")
    print(f"  confidence_score: {p['confidence_score']}")
    print(f"  validation_score: {p['validation_score']}")
    print(f"  validated:       {p['validated']}")
    print(f"  active:          {p['active']}")
else:
    print(f"\n  exists:          False")

# All current patterns
print(f"\n  All active patterns:")
all_pat = q("SELECT id, pattern_key, sample_size, confidence_score, validation_score, validated, active FROM semantic_patterns ORDER BY sample_size DESC")
for p in all_pat:
    print(f"    id={p['id']} key={str(p['pattern_key'])[:65]} sample={p['sample_size']} conf={p['confidence_score']} val_score={p['validation_score']} validated={p['validated']} active={p['active']}")

# Bearish episodes resolution status
print(f"\n  Bearish episode resolution:")
bear_res = q("SELECT resolved, COUNT(*) as cnt FROM agent_episodes WHERE analyst_consensus='bearish' GROUP BY resolved ORDER BY resolved")
for r in bear_res:
    print(f"    resolved={r['resolved']}: {r['cnt']}")

# Total bearish episodes
bear_total = q("SELECT COUNT(*) as c FROM agent_episodes WHERE analyst_consensus='bearish'")[0]['c']
print(f"    total bearish episodes: {bear_total}")

print("\n" + "=" * 70)
print("E: PHASE 8.3 GATE RECALCULATION")
print("=" * 70)

validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE validated=TRUE")[0]['c']
print(f"\n  1. validated_patterns >= 3:  {validated}  {'✓' if validated >= 3 else '✗'}")

resolved_pairs = len(pairs)
print(f"  2. resolved_pairs >= 10:    {resolved_pairs}  {'✓' if resolved_pairs >= 10 else '✗'}")

avgc_row = q("SELECT AVG(memory_contribution_score) as avgc FROM memory_attributions WHERE outcome_quality NOT IN ('pending')")
avgc = float(avgc_row[0]['avgc']) if avgc_row[0]['avgc'] is not None else 0.0
print(f"  3. avg_contribution > 0:    {round(avgc, 4)}  {'✓' if avgc > 0 else '✗'}")

dp = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']
da = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]['c']
dc = q("SELECT COUNT(DISTINCT analyst_consensus) as c FROM agent_episodes")[0]['c']
diversity = dp * dc * min(da, 5)
print(f"  4. diversity >= 50:         {diversity}  {'✓' if diversity >= 50 else '✗'}")
print(f"     (patterns={dp} * analyst_consensus={dc} * min(actions={da},5))")

gates_met = sum([validated >= 3, resolved_pairs >= 10, avgc > 0, diversity >= 50])
print(f"\n  gates_passed: {gates_met}/4")

print("\n" + "=" * 70)
print("F: VERDICT")
print("=" * 70)

# Compare with before metrics
print(f"""
  BEFORE PATCH (Phase 8.2.14-15):
    resolved shadow obs:  0
    resolved pairs:       0
    validated patterns:   2
    bearish pattern:      NOT_FOUND
    gates met:            1/4

  AFTER PATCH (Phase 8.2.19):
    resolved shadow obs:  {resolved}
    resolved pairs:       {resolved_pairs}
    validated patterns:   {validated}
    bearish pattern:      {'PRESENT' if bearish_pat else 'NOT_FOUND'}
    gates met:            {gates_met}/4

  SHADOW RESOLUTION:     {'ENABLED' if resolved > 0 else 'STILL BLOCKED'}
  PAIR FORMATION:        {'ACTIVE' if resolved_pairs > 0 else 'STILL BLOCKED'}
""")

if resolved > 0 and resolved_pairs > 0:
    print("  VERDICT: RECOVERY_SUCCESS")
    print(f"  The patch resolved {resolved} shadow observations and generated")
    print(f"  {resolved_pairs} resolved shadow-attribution pairs.")
elif resolved > 0:
    print("  VERDICT: RECOVERY_PARTIAL")
    print(f"  Shadow resolution works ({resolved} resolved) but no pairs yet.")
else:
    print("  VERDICT: RECOVERY_FAILED")
    print("  Shadow resolution is still not functioning.")

conn.close()
print("\n" + "=" * 70)
print("Phase 8.2.19 audit complete. No code changes made.")
print("=" * 70)