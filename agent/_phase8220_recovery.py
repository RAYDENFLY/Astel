"""
Phase 8.2.20 — Post-Restart Shadow Recovery Verification
Uses live PostgreSQL. Audit only. No code changes.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone
import subprocess

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

def q(sql):
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

now = datetime.now(tz=timezone.utc)
now_str = str(now)[:19]

print("=" * 70)
print("PHASE 8.2.20 — POST-RESTART SHADOW RECOVERY VERIFICATION")
print(f"Timestamp: {now_str} UTC")
print("=" * 70)

print("\n" + "=" * 70)
print("A: RUNTIME VERIFICATION")
print("=" * 70)

# Check if agent is running
try:
    result = subprocess.run(
        ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
        capture_output=True, text=True, timeout=5
    )
    python_pids = []
    for line in result.stdout.split('\n'):
        if 'python.exe' in line and 'PID' not in line:
            parts = line.replace('"', '').split(',')
            if len(parts) >= 2:
                python_pids.append(parts[1].strip())
    print(f"\n  Python processes running: {len(python_pids)}")
    print(f"  PIDs: {', '.join(python_pids) if python_pids else 'none'}")
except Exception as e:
    print(f"\n  Error checking processes: {e}")

# Check latest plan timestamp
plans = q("SELECT id, ts FROM agent_plans ORDER BY ts DESC LIMIT 3")
print(f"\n  Latest 3 plans:")
for p in plans:
    print(f"    plan_id={p['id']} ts={str(p['ts'])[:19]}")

# Check if any shadow observation has resolved_at set
resolved_when = q("""
    SELECT MIN(resolved_at) as first_res, MAX(resolved_at) as last_res, COUNT(*) as cnt
    FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL
""")[0]
print(f"\n  Shadow observations with resolved_at set: {resolved_when['cnt']}")
if resolved_when['first_res']:
    print(f"  First ever resolution: {str(resolved_when['first_res'])[:19]}")
    print(f"  Latest resolution:     {str(resolved_when['last_res'])[:19]}")

# Detect restart: look for a gap in the plan timeline or a new agent marker
print(f"\n  RESTART DETECTED: {'YES' if resolved_when['cnt'] > 0 else 'NO'}")
print(f"  (patch was applied to shadow.py at ~4:13 UTC)")

print("\n" + "=" * 70)
print("B: SHADOW RECOVERY (BEFORE vs AFTER)")
print("=" * 70)

rows = q("SELECT status, COUNT(*) as cnt FROM shadow_observations GROUP BY status ORDER BY cnt DESC")
total = sum(r['cnt'] for r in rows)
resolved = sum(r['cnt'] for r in rows if r['status'] == 'RESOLVED')
pending = sum(r['cnt'] for r in rows if r['status'] == 'PENDING_24H')

print(f"""
  ┌─────────────────────┬──────────┬──────────┬──────────┐
  │ Metric              │ Before   │ After    │ Delta    │
  ├─────────────────────┼──────────┼──────────┼──────────┤""")
print(f"  │ RESOLVED            │ {0:>8} │ {resolved:>8} │ {resolved:>+8} │")
print(f"  │ PENDING_24H         │ {535:>8} │ {pending:>8} │ {pending - 535:>+8} │")
print(f"  │ TOTAL               │ {535:>8} │ {total:>8} │ {total - 535:>+8} │")
print(f"  └─────────────────────┴──────────┴──────────┴──────────┘")
print(f"\n  resolution_rate_pct: {round(resolved/max(1,total)*100, 2)}%")

# Show some resolved observations with timestamps
if resolved > 0:
    print(f"\n  Sample of resolved observations:")
    resolved_samples = q("""
        SELECT id, plan_id, ts, agreement, resolved_at, equity_change_24h, asset_return_24h
        FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL
        ORDER BY ts DESC LIMIT 10
    """)
    for r in resolved_samples:
        print(f"    id={r['id']} plan={r['plan_id']} ts={str(r['ts'])[:19]} "
              f"agreement={r['agreement']} resolved_at={str(r['resolved_at'])[:19] if r['resolved_at'] else 'N/A'} "
              f"eq_change={r['equity_change_24h']}")

print("\n" + "=" * 70)
print("C: PAIR GENERATION (BEFORE vs AFTER)")
print("=" * 70)

pairs = q("""
    SELECT so.id as shadow_id, so.plan_id, so.agreement, so.ts as shadow_ts,
           ma.id as attr_id, ma.outcome_quality, ma.memory_contribution_score
    FROM shadow_observations so
    JOIN memory_attributions ma ON ma.plan_id = so.plan_id
    WHERE so.status = 'RESOLVED'
    ORDER BY so.ts
""")

tot_obs = q("SELECT COUNT(*) as c FROM shadow_observations")[0]['c']
pair_coverage = round(len(pairs)/max(1,tot_obs)*100, 2) if tot_obs > 0 else 0.0

print(f"""
  ┌─────────────────────┬──────────┬──────────┬──────────┐
  │ Metric              │ Before   │ After    │ Delta    │
  ├─────────────────────┼──────────┼──────────┼──────────┤""")
print(f"  │ Resolved pairs      │ {0:>8} │ {len(pairs):>8} │ {len(pairs):>+8} │")
print(f"  │ Pair coverage %     │ {0.0:>8} │ {pair_coverage:>8} │ {pair_coverage:>+8} │")
print(f"  └─────────────────────┴──────────┴──────────┴──────────┘")

if pairs:
    print(f"\n  first_pair_timestamp:  {str(pairs[0]['shadow_ts'])[:19]}")
    print(f"  latest_pair_timestamp: {str(pairs[-1]['shadow_ts'])[:19]}")
    print(f"\n  All resolved pairs:")
    for r in pairs:
        ts = str(r['shadow_ts'])[:19] if r['shadow_ts'] else 'N/A'
        print(f"    shadow_id={r['shadow_id']} plan={r['plan_id']} attr_id={r['attr_id']} "
              f"outcome={r['outcome_quality']} contrib={r['memory_contribution_score']} ts={ts}")
else:
    print(f"\n  No resolved pairs yet.")

print("\n" + "=" * 70)
print("D: RECOVERY THROUGHPUT")
print("=" * 70)

# Count resolved in last 5/60 min
r5 = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL AND EXTRACT(EPOCH FROM (NOW() - resolved_at)) < 300")[0]['c']
r1h = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL AND EXTRACT(EPOCH FROM (NOW() - resolved_at)) < 3600")[0]['c']

# Still eligible but pending
old_p = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='PENDING_24H' AND EXTRACT(EPOCH FROM (NOW() - ts)) > 86400")[0]['c']
young_p = q("SELECT COUNT(*) as c FROM shadow_observations WHERE status='PENDING_24H' AND EXTRACT(EPOCH FROM (NOW() - ts)) <= 86400")[0]['c']

print(f"""
  ┌─────────────────────────────┬────────────┐
  │ Metric                      │ Value      │
  ├─────────────────────────────┼────────────┤""")
print(f"  │ Resolved in last 5 min    │ {r5:>10} │")
print(f"  │ Resolved in last hour     │ {r1h:>10} │")
print(f"  │ Still eligible (>24h)     │ {old_p:>10} │")
print(f"  │ Too young (<=24h)         │ {young_p:>10} │")
print(f"  │ Total skipped (None/bad)  │ {total - resolved - pending:>10} │")
print(f"  └─────────────────────────────┴────────────┘")

print("\n" + "=" * 70)
print("E: BEARISH PATTERN STATUS")
print("=" * 70)

pat = q("SELECT * FROM semantic_patterns WHERE pattern_key = 'TIGHTEN_RISK|CONSERVATIVE|bearish|unknown'")
if pat:
    p = pat[0]
    print(f"\n  exists:          True")
    print(f"  pattern_id:      {p['id']}")
    print(f"  sample_size:     {p['sample_size']}")
    print(f"  confidence_score: {p['confidence_score']}")
    print(f"  validation_score: {p['validation_score']}")
    print(f"  validated:       {p['validated']}")
    print(f"  active:          {p['active']}")
else:
    print(f"\n  exists:          False")

# All patterns
print(f"\n  All patterns:")
all_p = q("SELECT id, pattern_key, sample_size, confidence_score, validation_score, validated, active FROM semantic_patterns ORDER BY sample_size DESC")
for p in all_p:
    print(f"    id={p['id']} key={str(p['pattern_key'])[:65]} sample={p['sample_size']} conf={p['confidence_score']} val_score={p['validation_score']} validated={p['validated']} active={p['active']}")

# Bearish episodes resolution
bear_res = q("SELECT resolved, COUNT(*) as cnt FROM agent_episodes WHERE analyst_consensus='bearish' GROUP BY resolved ORDER BY resolved")
print(f"\n  Bearish episode resolution:")
for r in bear_res:
    print(f"    resolved={r['resolved']}: {r['cnt']}")
bear_total = q("SELECT COUNT(*) as c FROM agent_episodes WHERE analyst_consensus='bearish'")[0]['c']
print(f"    total: {bear_total}")

print("\n" + "=" * 70)
print("F: PHASE 8.3 GATE RECALCULATION")
print("=" * 70)

validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE validated=TRUE")[0]['c']
resolved_pairs = len(pairs)
avgc = float(q("SELECT AVG(memory_contribution_score) as avgc FROM memory_attributions WHERE outcome_quality NOT IN ('pending')")[0]['avgc'] or 0.0)
dp = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]['c']
da = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]['c']
dc = q("SELECT COUNT(DISTINCT analyst_consensus) as c FROM agent_episodes")[0]['c']
diversity = dp * dc * min(da, 5)

print(f"""
  ┌─────────────────────────────┬──────────┬──────┐
  │ Gate                        │ Value    │ Pass │
  ├─────────────────────────────┼──────────┼──────┤""")
print(f"  │ 1. validated_patterns >= 3 │ {validated:>8} │ {'✓' if validated>=3 else '✗':>4} │")
print(f"  │ 2. resolved_pairs >= 10    │ {resolved_pairs:>8} │ {'✓' if resolved_pairs>=10 else '✗':>4} │")
print(f"  │ 3. avg_contribution > 0    │ {round(avgc, 4):>8} │ {'✓' if avgc>0 else '✗':>4} │")
print(f"  │ 4. diversity >= 50         │ {diversity:>8} │ {'✓' if diversity>=50 else '✗':>4} │")
print(f"  └─────────────────────────────┴──────────┴──────┘")
print(f"  gates_passed: {sum([validated>=3, resolved_pairs>=10, avgc>0, diversity>=50])}/4")

# Final comparison
print("\n" + "=" * 70)
print("G: VERDICT — BEFORE vs AFTER COMPARISON")
print("=" * 70)

print(f"""
  ┌─────────────────────────────┬──────────┬──────────┬───────────────┐
  │ Metric                      │ Before   │ After    │ Status        │
  ├─────────────────────────────┼──────────┼──────────┼───────────────┤
  │ RESOLVED shadow obs         │ {0:>8} │ {resolved:>8} │ {'FIXED!' if resolved>0 else 'STUCK':>13} │
  │ Resolved pairs              │ {0:>8} │ {resolved_pairs:>8} │ {'FIXED!' if resolved_pairs>0 else 'STUCK':>13} │
  │ Validated patterns          │ {2:>8} │ {validated:>8} │ {'NEW!' if validated>2 else 'SAME':>13} │
  │ Bearish pattern             │ {'NOT_FOUND':>8} │ {'PRESENT' if pat else 'NOT_FOUND':>8} │ {'MINED!' if pat else 'PENDING':>13} │
  │ Phase 8.3 gates             │ {1:>8} │ {sum([validated>=3, resolved_pairs>=10, avgc>0, diversity>=50]):>8} │ {'IMPROVED' if sum([validated>=3, resolved_pairs>=10, avgc>0, diversity>=50])>1 else 'SAME':>13} │
  └─────────────────────────────┴──────────┴──────────┴───────────────┘
""")

# Print verdict
if resolved > 0 and resolved_pairs > 0:
    print("VERDICT: RECOVERY_SUCCESS")
    print(f"The patch resolved {resolved} shadow observations and generated {resolved_pairs} pairs.")
elif resolved > 0:
    print("VERDICT: RECOVERY_PARTIAL")
    print(f"Shadow resolution running ({resolved} resolved) but pairs not yet generated.")
else:
    print("VERDICT: RECOVERY_FAILED")
    print("Shadow resolution still not functioning. Agent may not have restarted yet.")

conn.close()
print("\n" + "=" * 70)
print("Phase 8.2.20 audit complete. No code changes made.")
print("=" * 70)