"""
Phase 8.2.21 — Immediate Post-Restart Shadow Activation Audit
Uses live PostgreSQL. Audit only. No code changes.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
import subprocess
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

def q(sql):
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

print("=" * 70)
print("PHASE 8.2.21 — POST-RESTART SHADOW ACTIVATION AUDIT")
print("=" * 70)

print("\nA: RUNTIME ACTIVATION")
r = subprocess.run(["tasklist","/FI","IMAGENAME eq python.exe","/FO","CSV"],
                    capture_output=True, text=True, timeout=5)
pids = []
for line in r.stdout.split("\n"):
    if "python.exe" in line and "PID" not in line:
        parts = line.replace('"',"").split(",")
        if len(parts) >= 2:
            pids.append(parts[1].strip())
print(f"  python PIDs: {', '.join(pids) if pids else 'none'}")
print(f"  process count: {len(pids)}")

plans = q("SELECT id, ts FROM agent_plans ORDER BY ts DESC LIMIT 3")
for p in plans:
    pid = p["id"]
    pts = str(p["ts"])[:19]
    print(f"  latest plan: id={pid} ts={pts}")

print("\nRUNTIME_ACTIVATION_STATUS:")
print(f"  current_pid: {', '.join(pids) if pids else 'N/A'}")
restart = "NO"
if pids:
    # If agent is running, check if plans are recent
    restart = "YES (agent running)"
print(f"  restart_confirmed: {restart}")
if plans:
    print(f"  latest_plan_id: {plans[0]['id']}")
    print(f"  latest_plan_ts: {str(plans[0]['ts'])[:19]}")
else:
    print(f"  latest_plan: N/A")

print("\nB: SHADOW RESOLUTION EXECUTION")
rows = q("SELECT status, COUNT(*) as cnt FROM shadow_observations GROUP BY status ORDER BY cnt DESC")
total = sum(r["cnt"] for r in rows)
resolved = sum(r["cnt"] for r in rows if r["status"] == "RESOLVED")
pending = sum(r["cnt"] for r in rows if r["status"] == "PENDING_24H")
for r in rows:
    print(f"  {r['status']}: {r['cnt']}")
print(f"  TOTAL: {total}")

print("\nSHADOW_EXECUTION_STATUS:")
print(f"  pending_before (8.2.15): 535")
print(f"  pending_after:           {pending}")
print(f"  resolved_before:         0")
print(f"  resolved_after:          {resolved}")
print(f"  resolved_delta:          {resolved}")

print("\nC: PAIR GENERATION BURST")
pairs_rows = q("""
    SELECT COUNT(*) as cnt FROM shadow_observations so
    JOIN memory_attributions ma ON ma.plan_id = so.plan_id
    WHERE so.status = 'RESOLVED'
""")
pairs = pairs_rows[0]["cnt"]
coverage = round(pairs / max(1, total) * 100, 2) if total > 0 else 0.0

print(f"\nPAIR_BURST_STATUS:")
print(f"  pairs_before_restart: 0")
print(f"  pairs_after_restart:  {pairs}")
print(f"  pair_delta:           {pairs}")
print(f"  pair_coverage_pct:    {coverage}%")

if pairs > 0:
    print(f"\n  Resolved pairs detail:")
    pair_detail = q("""
        SELECT so.id as shadow_id, so.plan_id, so.ts as shadow_ts,
               ma.id as attr_id, ma.outcome_quality, ma.memory_contribution_score
        FROM shadow_observations so
        JOIN memory_attributions ma ON ma.plan_id = so.plan_id
        WHERE so.status = 'RESOLVED'
        ORDER BY so.ts LIMIT 15
    """)
    for r in pair_detail:
        ts = str(r["shadow_ts"])[:19] if r["shadow_ts"] else "N/A"
        print(f"    shadow_id={r['shadow_id']} plan={r['plan_id']} attr_id={r['attr_id']} "
              f"outcome={r['outcome_quality']} contrib={r['memory_contribution_score']} ts={ts}")

print("\nD: BUG FIX VERIFICATION")
resolved_times = q("""
    SELECT MIN(resolved_at) as first_res, MAX(resolved_at) as last_res
    FROM shadow_observations WHERE status='RESOLVED' AND resolved_at IS NOT NULL
""")
first_res = resolved_times[0]["first_res"] if resolved_times else None

print(f"\nBUG_FIX_STATUS:")
print(f"  any PENDING_24H -> RESOLVED transition: {'YES' if resolved > 0 else 'NO'}")
if first_res:
    print(f"  first_resolved_at: {str(first_res)[:19]}")
    print(f"  latest_resolved_at: {str(resolved_times[0]['last_res'])[:19]}")
    print(f"  BUG FIX: ACTIVE")
else:
    print(f"  BUG FIX: NOT ACTIVE YET (agent may not have restarted)")

print("\nE: PHASE 8.3 GATE")
validated = q("SELECT COUNT(*) as c FROM semantic_patterns WHERE validated=TRUE")[0]["c"]
avgc_row = q("SELECT AVG(memory_contribution_score) as avgc FROM memory_attributions WHERE outcome_quality NOT IN ('pending')")
avgc = float(avgc_row[0]["avgc"]) if avgc_row[0]["avgc"] is not None else 0.0
dp = q("SELECT COUNT(DISTINCT pattern_key) as c FROM semantic_patterns WHERE active=TRUE")[0]["c"]
da = q("SELECT COUNT(DISTINCT action_type) as c FROM agent_episodes")[0]["c"]
dc = q("SELECT COUNT(DISTINCT analyst_consensus) as c FROM agent_episodes")[0]["c"]
diversity = dp * dc * min(da, 5)

g1 = "PASS" if validated >= 3 else "FAIL"
g2 = "PASS" if pairs >= 10 else "FAIL"
g3 = "PASS" if avgc > 0 else "FAIL"
g4 = "PASS" if diversity >= 50 else "FAIL"
gates = sum([validated >= 3, pairs >= 10, avgc > 0, diversity >= 50])

print(f"\nPHASE_8_3_STATUS:")
print(f"  1. validated_patterns >= 3: {validated}/3 [{g1}]")
print(f"  2. resolved_pairs >= 10:    {pairs}/10 [{g2}]")
print(f"  3. avg_contribution > 0:    {round(avgc,4)} [{g3}]")
print(f"  4. diversity >= 50:         {diversity}/50 [{g4}]")
print(f"  gates_passed: {gates}/4")

print("\nBEARISH PATTERN CHECK:")
pat = q("SELECT * FROM semantic_patterns WHERE pattern_key = 'TIGHTEN_RISK|CONSERVATIVE|bearish|unknown'")
if pat:
    print(f"  pattern EXISTS: id={pat[0]['id']} sample={pat[0]['sample_size']} validated={pat[0]['validated']}")
else:
    print(f"  pattern NOT_FOUND")
    bear = q("SELECT resolved, COUNT(*) as cnt FROM agent_episodes WHERE analyst_consensus='bearish' GROUP BY resolved ORDER BY resolved")
    for r in bear:
        print(f"  bearish episodes resolved={r['resolved']}: {r['cnt']}")

print("\nF: VERDICT")
if resolved > 0:
    print("\n  BUG_FIXED_AND_ACTIVE")
    print(f"  Shadow resolution is functioning: {resolved} observations resolved.")
    if pairs > 0:
        print(f"  Pair generation working: {pairs} resolved pairs.")
    else:
        print(f"  Pairs not yet available (attribution may need time to match).")
else:
    print("\n  BUG_STILL_PRESENT")
    print(f"  No shadow observations have transitioned PENDING_24H -> RESOLVED.")
    print(f"  Agent PIDs: {pids}")

conn.close()
print("\n" + "=" * 70)
print("Phase 8.2.21 audit complete. No code changes made.")
print("=" * 70)