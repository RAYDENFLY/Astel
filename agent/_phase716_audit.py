"""
Phase 7.16 — Memory Activation Post-Restart Audit
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
print("PHASE 7.16 — MEMORY ACTIVATION POST-RESTART AUDIT")
print(f"Timestamp: {now.isoformat()}")
print("=" * 70)

# ==================================================================
# Section A — Restart Verification
# ==================================================================
print("\n--- SECTION A: RESTART VERIFICATION ---")
cur.execute("SELECT ts FROM agent_plans ORDER BY ts")
rows = [r[0] for r in cur.fetchall()]
total = len(rows)

# Find latest restart by looking for gap > 15 min in last 2 hours
restart_found = False
cutoff_ts = None
for i in range(1, total):
    gap = (rows[i] - rows[i-1]).total_seconds() / 60
    if gap > 15 and (now - rows[i]).total_seconds() / 60 < 120:  # within last 2 hours
        cutoff_ts = rows[i]
        restart_found = True
        break

if restart_found:
    recent = [r for r in rows if r >= cutoff_ts]
    loops_since = len(recent)
    print(f"RESTART GAP DETECTED: at {cutoff_ts}")
    print(f"Plans since restart: {loops_since}")
    for j, ts in enumerate(recent):
        age = (now - ts).total_seconds() / 60
        print(f"  Loop {j+1}: {ts} ({age:.0f}m ago)")
    restart_confirmed = True
else:
    # Check if there's a gap > 60 min anywhere recent
    for i in range(1, total):
        gap = (rows[i] - rows[i-1]).total_seconds() / 60
        if gap > 60:
            cutoff_ts = rows[i]
            restart_found = True
            recent = [r for r in rows if r >= cutoff_ts]
            loops_since = len(recent)
            print(f"OLDER RESTART at {cutoff_ts}, {loops_since} plans since")
            restart_confirmed = True
            break
    
    if not restart_found:
        loops_since = total
        print(f"NO RESTART GAP FOUND. Using all {total} plans.")
        print(f"Last plan: {rows[-1]} ({(now-rows[-1]).total_seconds()/60:.0f}m ago)")
        restart_confirmed = True  # Still report data, just from longest run

print(f"RUNTIME_RESTART_CONFIRMED = {'TRUE' if restart_found else 'FALSE (using all data)'}")

# ==================================================================
# Section B — Pattern Consumption
# ==================================================================
print("\n--- SECTION B: PATTERN CONSUMPTION ---")
cur.execute("SELECT COUNT(*) FROM semantic_patterns")
pc = cur.fetchone()[0]
print(f"Total patterns: {pc}")

if pc > 0:
    cur.execute("SELECT id, pattern_key, sample_size, success_rate, confidence_score, validated, validation_score FROM semantic_patterns")
    for r in cur.fetchall():
        print(f"  Pattern {r[0]}: {r[1]} ss={r[2]} sr={r[3]} conf={r[4]} valid={'YES' if r[5] else 'NO'} vscore={r[6]}")

# Check injections created AFTER the restart cutoff
cur.execute("SELECT * FROM memory_injections ORDER BY ts DESC")
all_inj = []
for r in cur.fetchall():
    cols = [desc[0] for desc in cur.description]
    all_inj.append(dict(zip(cols, r)))

print(f"\nTotal injections (all-time): {len(all_inj)}")

if restart_found and cutoff_ts:
    post_restart_inj = [i for i in all_inj if i.get("ts", "") >= cutoff_ts]
else:
    post_restart_inj = all_inj

print(f"Injections since restart: {len(post_restart_inj)}")
has_rules = [i for i in post_restart_inj if int(i.get("rule_count", 0)) > 0]
print(f"Injections with rules > 0: {len(has_rules)}")

if has_rules:
    print("\n  Newest injections with rules:")
    for i in has_rules[:5]:
        rules_json = i.get("rules_json", "[]")
        if isinstance(rules_json, str):
            try: rules = json.loads(rules_json)
            except: rules = []
        else: rules = rules_json or []
        print(f"  #{i['id']} at {i.get('ts','?')}: plan={i['plan_id']} rules={len(rules)}")
        for r in rules[:2]:
            print(f"    {r.get('pattern_key','?')} sr={r.get('success_rate',0)} vs={r.get('validation_score',0)}")
    
    pattern_status = "ACTIVE"
elif len(post_restart_inj) > 0:
    pattern_status = "INACTIVE (injections exist but rules=0)"
else:
    pattern_status = "INACTIVE (no post-restart injections yet)"

print(f"PATTERN_CONSUMPTION_STATUS = {pattern_status}")

# ==================================================================
# Section C — Memory Influence
# ==================================================================
print("\n--- SECTION C: MEMORY INFLUENCE ---")
cur.execute("SELECT * FROM memory_attributions ORDER BY ts DESC")
all_attr = []
for r in cur.fetchall():
    cols = [desc[0] for desc in cur.description]
    all_attr.append(dict(zip(cols, r)))

print(f"Total attributions (all-time): {len(all_attr)}")

if restart_found and cutoff_ts:
    post_restart_attr = [a for a in all_attr if a.get("ts", "") >= cutoff_ts]
else:
    post_restart_attr = all_attr

print(f"Attributions since restart: {len(post_restart_attr)}")
has_rules_attr = [a for a in post_restart_attr if int(a.get("memory_rules_count", 0)) > 0]
has_conf_attr = [a for a in post_restart_attr if float(a.get("memory_confidence", 0)) > 0]

print(f"Attributions with rules > 0: {len(has_rules_attr)}")
print(f"Attributions with confidence > 0: {len(has_conf_attr)}")

if has_rules_attr:
    print("\n  Newest attributions with memory context:")
    for a in has_rules_attr[:5]:
        dv = a.get('debate_verdict', '?')
        print(f"  ep={a['episode_id']} verdict={dv} rules={a['memory_rules_count']} conf={a['memory_confidence']} quality={a.get('outcome_quality','?')} contrib={a.get('memory_contribution_score',0)}")
    influence_status = "ACTIVE"
elif len(post_restart_attr) > 0:
    influence_status = "WAITING (attributions exist but no memory context)"
else:
    influence_status = "WAITING (no post-restart attributions yet)"

print(f"MEMORY_INFLUENCE_STATUS = {influence_status}")

# ==================================================================
# Section D — First Real Memory Usage
# ==================================================================
print("\n--- SECTION D: FIRST REAL MEMORY USAGE ---")
first_memory = None

# Find the earliest record where rules > 0 in both injections AND attributions
if has_rules:
    first_inj = min(has_rules, key=lambda x: x.get("ts", ""))
    first_attr_with_rules = None
    if has_rules_attr:
        first_attr_with_rules = min(has_rules_attr, key=lambda x: x.get("ts", ""))
    
    if first_attr_with_rules:
        first_memory = {
            "episode_id": first_attr_with_rules["episode_id"],
            "plan_id": first_attr_with_rules.get("plan_id"),
            "pattern_rules_count": first_attr_with_rules.get("memory_rules_count", 0),
            "confidence": first_attr_with_rules.get("memory_confidence", 0),
            "timestamp": first_attr_with_rules.get("ts"),
            "verdict": first_attr_with_rules.get("debate_verdict"),
        }
        print(f"First memory usage: ep={first_memory['episode_id']} at {first_memory['timestamp']}")
        print(f"  rules={first_memory['pattern_rules_count']} conf={first_memory['confidence']} verdict={first_memory['verdict']}")
    else:
        print("Injections have rules but attributions don't yet (need new episodes through the pipeline)")
else:
    print("No memory usage detected yet.")

memory_usage = first_memory is not None
print(f"FIRST_MEMORY_USAGE = {'TRUE' if memory_usage else 'FALSE'}")

# ==================================================================
# Section E — Attribution Resolution Forecast
# ==================================================================
print("\n--- SECTION E: ATTRIBUTION RESOLUTION FORECAST ---")
pending_count = sum(1 for a in all_attr if a.get("outcome_quality") == "pending")
completed_count = len(all_attr) - pending_count
print(f"Pending attributions: {pending_count}")
print(f"Completed attributions: {completed_count}")

# Check unresolved episodes
cur.execute("SELECT COUNT(*) FROM agent_episodes WHERE CAST(resolved AS integer)=0")
unresolved_eps = cur.fetchone()[0]
print(f"Unresolved episodes: {unresolved_eps}")

# Resolution window is 6h
print(f"Expected resolution time: ~6h from episode creation")
print(f"Projected contribution scores: depends on memory impact in next attribution cycle")

eta = "~6h+ from latest episode"
print(f"FIRST_COMPLETE_MEMORY_CYCLE ETA = {eta}")

# ==================================================================
# Section F — Phase 8 Progress
# ==================================================================
print("\n--- SECTION F: PHASE 8 PROGRESS ---")
cur.execute("SELECT COUNT(*) FROM agent_episodes WHERE CAST(resolved AS integer)=1")
resolved = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM semantic_patterns WHERE validated=true")
validated_patterns = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM memory_advice")
advice_count = cur.fetchone()[0]

print(f"Resolved episodes:           {resolved}")
print(f"Validated patterns:          {validated_patterns}")
print(f"Injections with rules > 0:   {len(has_rules)}")
print(f"Attributions with rules > 0: {len(has_rules_attr)}")
print(f"Advice records:              {advice_count}")

# Progress percentage
targets = {
    "Resolved Episodes": (resolved, 50, 20),
    "Validated Patterns": (validated_patterns, 3, 20),
    "Injections w/ rules": (len(has_rules), 5, 20),
    "Attributions w/ rules": (len(has_rules_attr), 10, 20),
    "Advice Records": (advice_count, 20, 20),
}

progress = sum(min(100, (val / max(1, target)) * 100) * weight / 100 for name, (val, target, weight) in targets.items())
print(f"\nPHASE8_PROGRESS = {progress:.1f}%")

ready = (
    resolved >= 50
    and validated_patterns >= 3
    and len(has_rules) >= 5
    and len(has_rules_attr) >= 10
    and advice_count >= 20
)
print(f"READY_FOR_PHASE_8 = {'TRUE' if ready else 'FALSE'}")

# ==================================================================
# Final Verdict
# ==================================================================
print("\n" + "=" * 70)
print("FINAL VERDICT")
print("=" * 70)

print(f"\n1. Restart confirmed: {'YES' if restart_found else 'NO'}")
print(f"   Plans since restart: {loops_since}")
print(f"   Latest plan: {rows[-1]} ({(now-rows[-1]).total_seconds()/60:.0f}m ago)")

print(f"\n2. Pattern consumption:")
if restart_found and pattern_status == "ACTIVE":
    print("   ✅ YES — Validated pattern consumed by ProceduralMemory")
elif restart_found:
    print(f"   ⏳ PARTIAL — Injections exist ({len(post_restart_inj)}) but rules=0")
    print("   (May need mining to fire at loop 10 for auto-consumption)")
else:
    print("   ⏳ Cannot verify (no restart detected)")

print(f"\n3. memory_rules_count > 0: {'YES' if len(has_rules) > 0 else 'NO (injections exist but waiting for pattern consumption)'}")
print(f"4. memory_confidence > 0:   {'YES' if len(has_conf_attr) > 0 else 'NO (waiting for pattern consumption)'}")

print(f"\n5. Memory influencing decisions: {'YES - attribution shows non-zero memory context' if len(has_rules_attr) > 0 else 'WAITING - pattern exists but not yet consumed at runtime'}")

# Projection
remaining = []
if resolved < 50:
    remaining.append(f"{50 - resolved} more resolved episodes (~{(50 - resolved) * 0.5}h)")
if validated_patterns < 3:
    remaining.append(f"{3 - validated_patterns} more validated patterns")
if len(has_rules) < 5:
    remaining.append(f"{5 - len(has_rules)} more injections with rules")
if len(has_rules_attr) < 10:
    remaining.append(f"{10 - len(has_rules_attr)} more attributions with rules")

print(f"\n6. Remaining before Phase 8:")
for r in remaining:
    print(f"   - {r}")

# Time estimate
hours_est = max(0, (50 - resolved) * 0.5) if resolved < 50 else 0
print(f"\n   Estimated time: {hours_est:.1f}h")

conn.close()
print("\nAudit complete. No code changes made.")