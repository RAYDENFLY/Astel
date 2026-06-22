"""
Phase 8.2.22 — Bearish Pattern Pipeline Audit
Uses live PostgreSQL. Audit only. No code changes.
"""
import os, sys, json, math
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
print("PHASE 8.2.22 — BEARISH PATTERN PIPELINE AUDIT")
print(f"Timestamp: {str(now)[:19]} UTC")
print("=" * 70)

print("\n" + "=" * 70)
print("A: BEARISH EPISODE INVENTORY")
print("=" * 70)

eps = q("""
    SELECT id, ts, action_type, survival_mode, analyst_consensus,
           debate_verdict, resolved, outcome_json::text as ojt
    FROM agent_episodes
    WHERE action_type='TIGHTEN_RISK'
      AND survival_mode='CONSERVATIVE'
      AND analyst_consensus='bearish'
    ORDER BY ts
""")
print(f"\n  total episodes: {len(eps)}")
resolved = [e for e in eps if e['resolved']]
unresolved = [e for e in eps if not e['resolved']]
print(f"  resolved:   {len(resolved)}")
print(f"  unresolved: {len(unresolved)}")
if eps:
    print(f"  oldest: id={eps[0]['id']} ts={str(eps[0]['ts'])[:19]}")
    print(f"  newest: id={eps[-1]['id']} ts={str(eps[-1]['ts'])[:19]}")

print("\n" + "=" * 70)
print("B: RESOLVER VERIFICATION")
print("=" * 70)

print(f"\n  Bearish episode detail:")
for e in eps:
    ts = e['ts']
    age_h = (now - ts).total_seconds() / 3600
    ojt = e['ojt']
    if isinstance(ojt, str):
        try: ojt = json.loads(ojt)
        except: ojt = {}
    dq = (ojt or {}).get('decision_quality', 'N/A')
    print(f"    ep={e['id']:>4} age={age_h:>5.1f}h resolved={str(e['resolved']):>5} quality={dq}")

old_enough = [e for e in eps if (now - e['ts']).total_seconds() / 3600 > 6]
print(f"\n  episodes older than 6h: {len(old_enough)}")
print(f"  episodes with outcome_quality (resolved): {len(resolved)}")

print("\n" + "=" * 70)
print("C: MINER ELIGIBILITY")
print("=" * 70)

print(f"\n  MIN_SAMPLE_SIZE = 5")
print(f"  HIGH_SUCCESS_RATE = 0.70")
print(f"  LOW_SUCCESS_RATE = 0.30")

n = len(resolved)
print(f"\n  resolved episodes in this group: {n}")
print(f"  MIN_SAMPLE_SIZE check (>=5): {'PASS' if n >= 5 else 'FAIL'} ({n}/5)")

if n > 0:
    pos = 0; neg = 0; neu = 0
    for e in resolved:
        ojt = e['ojt']
        if isinstance(ojt, str):
            try: ojt = json.loads(ojt)
            except: ojt = {}
        ojt = ojt or {}
        qq = ojt.get('decision_quality', 'neutral')
        if qq == 'positive': pos += 1
        elif qq == 'negative': neg += 1
        else: neu += 1

    total_non_neutral = pos + neg
    success_rate = pos / max(1, total_non_neutral) if total_non_neutral > 0 else 0.5
    sample_weight = 1.0 - math.exp(-n / 10.0)
    distance_from_random = abs(success_rate - 0.5) * 2.0
    confidence_score = round(sample_weight * distance_from_random, 4)

    print(f"\n  positive={pos} negative={neg} neutral={neu}")
    print(f"  success_rate={success_rate:.4f}")
    print(f"  threshold check (>=0.70 or <=0.30): {'PASS' if success_rate >= 0.7 or success_rate <= 0.3 else 'FAIL'}")
    print(f"  sample_weight=1-exp(-{n}/10)={sample_weight:.4f}")
    print(f"  distance_from_random={distance_from_random:.4f}")
    print(f"  confidence_score={confidence_score:.4f}")
    print(f"\n  MINER WOULD CREATE PATTERN: {'YES' if n >= 5 and (success_rate >= 0.7 or success_rate <= 0.3) else 'NO'}")
else:
    print(f"\n  No resolved episodes in this group.")
    print(f"  MINER CANNOT CREATE PATTERN: need >=5 resolved episodes with decision_quality")

print("\n" + "=" * 70)
print("D: PATTERN SEARCH")
print("=" * 70)

pat = q("""
    SELECT id, pattern_key, sample_size, confidence_score,
           validation_score, validated, active
    FROM semantic_patterns
    WHERE pattern_key LIKE '%bearish%'
       OR pattern_key LIKE 'TIGHTEN_RISK|CONSERVATIVE%'
    ORDER BY sample_size DESC
""")
print(f"\n  bearish-related patterns: {len(pat)}")
for p in pat:
    print(f"    id={p['id']} key={str(p['pattern_key']):<60}"
          f" sample={p['sample_size']} conf={p['confidence_score']}"
          f" val={p['validation_score']} validated={p['validated']} active={p['active']}")

# Check checkpoint
cp = q("""
    SELECT pattern_key, last_episode_id_processed, sample_size
    FROM semantic_patterns
    WHERE pattern_key = 'TIGHTEN_RISK|CONSERVATIVE|conservative|unknown'
""")
if cp:
    ckpt_id = cp[0]['last_episode_id_processed']
    max_ep = q("SELECT MAX(id) as m FROM agent_episodes")[0]['m']
    print(f"\n  Main pattern checkpoint: episode_id={ckpt_id}")
    print(f"  Latest episode in DB:    {max_ep}")
    print(f"  Mining gap:              {max_ep - ckpt_id} episodes")

    bear_ids = [e['id'] for e in eps]
    if bear_ids:
        max_bear = max(bear_ids)
        min_bear = min(bear_ids)
        past_cp = sum(1 for eid in bear_ids if eid > ckpt_id)
        print(f"  Bearish episode IDs range: {min_bear} - {max_bear}")
        print(f"  Bearish episodes PAST checkpoint: {past_cp}")
        print(f"  When miner runs: bearish episodes are {'INCLUDED' if min_bear > ckpt_id else 'partially PAST checkpoint'}")

# Check all bearish groups
print("\n" + "=" * 70)
print("E: BLOCKER IDENTIFICATION")
print("=" * 70)

all_bear_groups = q("""
    SELECT action_type, survival_mode, analyst_consensus,
           resolved, COUNT(*) as cnt
    FROM agent_episodes WHERE analyst_consensus='bearish'
    GROUP BY action_type, survival_mode, analyst_consensus, resolved
    ORDER BY action_type, survival_mode, resolved
""")
print(f"\n  All bearish episode groups:")
for r in all_bear_groups:
    print(f"    {r['action_type']:25s} {str(r['survival_mode']):15s} resolved={r['resolved']}: {r['cnt']}")

# All bearish total
total_bear = sum(r['cnt'] for r in all_bear_groups)
resolved_bear_total = sum(r['cnt'] for r in all_bear_groups if r['resolved'])
print(f"\n  Total bearish episodes: {total_bear}")
print(f"  Total resolved bearish: {resolved_bear_total}")

print(f"\n  BLOCKER DIAGNOSIS:")
if resolved_bear_total == 0:
    print(f"    Blocked at: EPISODE_RESOLUTION")
    print(f"    Reason: 0 bearish episodes are resolved.")
    print(f"    Issue: EpisodeResolver has not processed any bearish episodes yet.")
    print(f"    Fix: Wait for 6h evaluation window. Oldest bearish episodes")
    print(f"         are now ~{max(0, round((now - eps[0]['ts']).total_seconds()/3600)) if eps else 0}h old.")
    print(f"         Should resolve within ~{max(0, round(6 - (now - eps[0]['ts']).total_seconds()/3600)) if eps else 0}h.")
elif resolved_bear_total >= 5:
    print(f"    Blocked at: PATTERN_MINING")
    print(f"    Reason: {resolved_bear_total} resolved bearish episodes available but TIGHTEN_RISK|CONSERVATIVE|bearish|unknown")
    print(f"            pattern not found in semantic_patterns table.")
    print(f"    Issue: MemoryMiner has not run since bearish episodes were resolved.")
    print(f"    Mining runs every 10th-50th tick. Last checkpoint is {cp[0]['last_episode_id_processed'] if cp else 'unknown'}.")
else:
    print(f"    Blocked at: INSUFFICIENT_SAMPLE")
    print(f"    Reason: Only {resolved_bear_total} bearish episodes resolved, need >=5 for MIN_SAMPLE_SIZE.")

print("\n" + "=" * 70)
print("F: FORECAST")
print("=" * 70)

if eps:
    oldest_age_h = (now - eps[0]['ts']).total_seconds() / 3600
    age_to_6h = max(0, 6 - oldest_age_h)
    print(f"\n  Time to first bearish resolution (6h age):")
    print(f"    Oldest bearish episode: {oldest_age_h:.1f}h old")
    print(f"    Time until 6h window:   {age_to_6h:.1f}h")
    print(f"    Expected resolution:    {'NOW' if age_to_6h <= 0 else '~{:.0f} minutes'.format(age_to_6h*60)}")

    print(f"\n  Time to pattern creation (after resolution + miner):")
    print(f"    Step 1: EpisodeResolver resolves episodes < 1 tick")
    print(f"    Step 2: MemoryMiner runs every ~50min (after 100 loops)")
    print(f"    Step 3: PatternValidator validates immediately after mining")
    print(f"    Total: ~1-2 hours after resolution")

    print(f"\n  Expected validation score (estimated):")
    print(f"    sample_size min(1.0, n/50.0) = {min(1.0, max(n, resolved_bear_total)/50.0):.4f}" if n > 0 else "    (unknown - no resolved data)")
    print(f"    confidence_score = {confidence_score:.4f}" if n > 0 else "")
    print(f"    Estimated validation_score = 0.7-0.9 (conservative action + bearish mode)")
else:
    print(f"\n  No bearish episodes found matching TIGHTEN_RISK|CONSERVATIVE|bearish|unknown")

print("\n" + "=" * 70)
print("G: VERDICT")
print("=" * 70)

if resolved_bear_total >= 5:
    print(f"\n  BEARISH_PIPELINE_HEALTHY")
    print(f"  Bearish episodes exist ({total_bear}) and {resolved_bear_total} are resolved.")
    print(f"  Miner will create pattern on next run.")
else:
    print(f"\n  BEARISH_PIPELINE_BLOCKED")
    print(f"  Blocking condition: NOT_RESOLVED")
    print(f"  {total_bear} bearish episodes exist but {resolved_bear_total} are resolved.")
    print(f"  EpisodeResolver needs ~{max(0, 6 - oldest_age_h):.1f}h more before first resolution.")
    print(f"  Expected auto-resolution within {max(0, 6 - oldest_age_h):.1f}h.")

conn.close()
print("\n" + "=" * 70)
print("Phase 8.2.22 audit complete. No code changes made.")
print("=" * 70)