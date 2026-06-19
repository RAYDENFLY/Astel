"""
Phase 7.14 — Live Runtime Diagnosis
Audit only. No code modifications.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()
now = datetime.now(timezone.utc)

print("=" * 70)
print("PHASE 7.14 — LIVE RUNTIME DIAGNOSIS")
print(f"Timestamp: {now.isoformat()}")
print("=" * 70)

# Get all plan timestamps to find restart point
cur.execute("SELECT ts FROM agent_plans ORDER BY ts")
all_plans = [r[0] for r in cur.fetchall()]
total_plans = len(all_plans)

# Find the most recent gap > 10 min (restart point)
restart_idx = None
for i in range(1, total_plans):
    gap = (all_plans[i] - all_plans[i-1]).total_seconds() / 60
    if gap > 10:
        restart_idx = i
        restart_ts = all_plans[i]
        print(f"\nRESTART POINT at plan index {i}: {all_plans[i-1]} -> {all_plans[i]} (gap={gap:.0f} min)")

if restart_idx is None:
    print("\nNo restart gap found. Loop_count = total plans.")
    loops_since_restart = total_plans
    recent_plans = all_plans
else:
    recent_plans = all_plans[restart_idx:]
    loops_since_restart = len(recent_plans)
    print(f"Loops since restart: {loops_since_restart}")
    for j, ts in enumerate(recent_plans):
        age_min = (now - ts).total_seconds() / 60
        print(f"  Loop {j+1}: {ts} ({age_min:.0f} min ago)")

# Mining timing analysis
mining_interval = 10  # warm-up mode since loop_count <= 100
mod = loops_since_restart % mining_interval
next_trigger_loop = ((loops_since_restart // mining_interval) + 1) * mining_interval
eta_min = (next_trigger_loop - loops_since_restart) * 5

print(f"\n--- MINING ANALYSIS ---")
print(f"Total plans (all-time):  {total_plans}")
print(f"Plans since restart:     {loops_since_restart} (loop_count)")
print(f"Mining interval:         {mining_interval}")
print(f"Current modulo:          {loops_since_restart} % {mining_interval} = {mod}")
print(f"Next trigger:            loop {next_trigger_loop}")
print(f"ETA to next trigger:     {eta_min} min")

# Did mining fire at loop 10? 20? 30? 40?
if loops_since_restart >= 4:
    for trigger_loop in range(10, min(loops_since_restart + 10, 100), 10):
        if trigger_loop <= loops_since_restart:
            print(f"  Loop {trigger_loop}: SHOULD HAVE FIRED {'✅' if trigger_loop % 10 == 0 and trigger_loop <= loops_since_restart else '❌'}")
        else:
            print(f"  Loop {trigger_loop}: upcoming")

# Check patterns
print(f"\n--- PATTERN CHECK ---")
cur.execute("SELECT COUNT(*) FROM semantic_patterns")
pattern_count = cur.fetchone()[0]
print(f"Patterns in DB: {pattern_count}")

if pattern_count == 0 and loops_since_restart >= 10:
    print("CRITICAL: 10+ loops elapsed but no patterns!")
    print("Possible causes:")
    print("  1. MemoryMiner throwing silent exception")
    print("  2. Mining condition not met due to loop_count != plan count")
    print("  3. Resolved episodes missing decision_quality in outcome_json")
    
    # Check loop_count vs plan count
    print(f"\n  loop_count in agent starts at 0 and increments each tick")
    print(f"  After {loops_since_restart} plans, loop_count = {loops_since_restart}")
    print(f"  Checking: {loops_since_restart} % 10 = {loops_since_restart % 10}")
    print(f"  If modulo == 0 at loop 10, should have fired at restart + 10 ticks")
    print(f"  Current modulo = {mod} (need 0 to fire)")
    
    # Check one more thing - does MemoryMiner.mine_patterns return 0 gracefully?
    print(f"\n  If MemoryMiner.mine_patterns() returns 0 (no qualifying patterns),")
    print(f"  the code in agent.py doesn't log anything:")
    print(f"    if mined > 0:")
    print(f"        val_result = self._pattern_validator.validate_patterns()")
    print(f"        log.info(...)")
    print(f"  So 0 patterns means NO log message either.")
    print(f"  The 11 TIGHTEN_RISK episodes HAVE decision_quality='positive'")
    print(f"  So patterns SHOULD be created. Mining likely hasn't fired yet.")
elif pattern_count == 0 and loops_since_restart < 10:
    print(f"Expected: only {loops_since_restart} loops, need 10 for mining. Normal.")
elif pattern_count > 0:
    cur.execute("SELECT id, pattern_key, sample_size, success_rate, confidence_score, validated, first_seen FROM semantic_patterns ORDER BY first_seen")
    for r in cur.fetchall():
        print(f"  Pattern {r[0]}: {r[1]} ss={r[2]} sr={r[3]} conf={r[4]} valid={r[5]} created={r[6]}")

# Time estimates
print(f"\n--- TIMELINE ---")
if loops_since_restart >= 10:
    print(f"✅ Warm-up mining should have fired")
    print(f"❓ Patterns: {pattern_count}")
    if pattern_count == 0:
        print(f"⚠️  Mining fired at loop 10 but produced 0 patterns?")
        print(f"   Or loop_count < 10 still?")
else:
    loops_needed = 10 - loops_since_restart
    print(f"⏱ {loops_needed} more loops ({loops_needed * 5} min) until first mining")
    print(f"⏱ ETA first pattern: ~{loops_needed * 5} min")

conn.close()
print("\nAudit complete. No code changes.")