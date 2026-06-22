"""
Phase 8.2.15 — Pattern Mining & Resolution Diagnostics
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

def q(sql, params=None):
    if params: cur.execute(sql, params)
    else: cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

print("=" * 70)
print("PHASE 8.2.15 — PATTERN MINING & RESOLUTION DIAGNOSTICS")
print("=" * 70)

# B: Bearish Episode Eligibility
print("\n" + "=" * 70)
print("B: BEARISH EPISODE ELIGIBILITY")
print("=" * 70)

bearish_eps = q("""
    SELECT id, ts, action_type, survival_mode, analyst_consensus, debate_verdict, resolved, created_at
    FROM agent_episodes
    WHERE analyst_consensus = 'bearish'
    ORDER BY ts
""")
print(f"\nTotal bearish (analyst_consensus='bearish') episodes: {len(bearish_eps)}")
resolved_count = sum(1 for e in bearish_eps if e['resolved'])
unresolved_count = sum(1 for e in bearish_eps if not e['resolved'])
print(f"  Resolved: {resolved_count}")
print(f"  Unresolved: {unresolved_count}")

now = datetime.now(tz=timezone.utc)
if bearish_eps:
    oldest = bearish_eps[0]
    newest = bearish_eps[-1]
    oldest_ts = oldest['ts']
    newest_ts = newest['ts']
    
    # Parse timestamps
    def parse_ts(ts):
        s = str(ts).replace('Z', '+00:00').replace(' ', 'T')
        return datetime.fromisoformat(s)
    
    oldest_age_h = (now - parse_ts(oldest_ts)).total_seconds() / 3600
    newest_age_h = (now - parse_ts(newest_ts)).total_seconds() / 3600
    
    print(f"  Oldest: id={oldest['id']} ts={str(oldest_ts)[:19]} age={oldest_age_h:.1f}h resolved={oldest['resolved']}")
    print(f"  Newest: id={newest['id']} ts={str(newest_ts)[:19]} age={newest_age_h:.1f}h resolved={newest['resolved']}")

    # Show all bearish episodes with age and resolution status
    print(f"\n  All bearish episodes detail:")
    for e in bearish_eps:
        age_h = (now - parse_ts(e['ts'])).total_seconds() / 3600
        print(f"    id={e['id']:>4} ts={str(e['ts'])[:19]} age={age_h:>6.1f}h resolved={e['resolved']} action={e['action_type']}")
    
    # Determine if any bearish episodes qualify for mining TODAY
    # Mining requires: resolved=True, sample_size >= 5
    resolved_bearish = [e for e in bearish_eps if e['resolved']]
    print(f"\n  Bearish episodes that ARE resolved (eligible for mining): {len(resolved_bearish)}")
    if resolved_bearish:
        print(f"  Would qualify for MINING? {'YES' if len(resolved_bearish) >= 5 else 'NO (need 5 minimum)'}")
        print(f"  sample_size would be: {len(resolved_bearish)}")
    else:
        print(f"  NONE are resolved → mining would see 0 bearish episodes")

    # Check outcome_json of bearish episodes
    print(f"\n  Sample outcome_json from bearish episodes:")
    for e in bearish_eps[:5]:
        o = e.get('outcome_json', '{}')
        if isinstance(o, str):
            try: o = json.loads(o)
            except: o = {}
        dv = o.get('debate_verdict', 'N/A') if isinstance(o, dict) else 'N/A'
        dq = o.get('decision_quality', 'N/A') if isinstance(o, dict) else 'N/A'
        print(f"    ep={e['id']} debate_verdict_in_json={dv} decision_quality={dq}")

# Also check the existing pattern checkpoint
print(f"\n  Existing bearish-related pattern checkpoint:")
pat = q("SELECT pattern_key, sample_size, last_episode_id_processed FROM semantic_patterns WHERE pattern_key LIKE '%bearish%' OR pattern_key LIKE '%TIGHTEN_RISK|CONSERVATIVE%'")
for p in pat:
    print(f"    key={p['pattern_key']} sample={p['sample_size']} checkpoint={p['last_episode_id_processed']}")

# C: Shadow Resolution Window
print("\n" + "=" * 70)
print("C: SHADOW RESOLUTION WINDOW")
print("=" * 70)

# Check oldest shadow observations
oldest_shadows = q("""
    SELECT id, plan_id, ts, status, agreement, ts as ts_raw
    FROM shadow_observations
    ORDER BY ts ASC
    LIMIT 10
""")
print(f"\nOldest 10 shadow observations:")
for s in oldest_shadows:
    age_h = (now - parse_ts(s['ts'])).total_seconds() / 3600
    print(f"  id={s['id']:>4} plan={s['plan_id']} ts={str(s['ts'])[:19]} age={age_h:>6.1f}h status={s['status']} agreement={s['agreement']}")

# Show age distribution of shadow obs
age_dist = q("""
    SELECT 
        CASE 
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 3600 THEN '0-1h'
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 7200 THEN '1-2h'
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 14400 THEN '2-4h'
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 28800 THEN '4-8h'
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 43200 THEN '8-12h'
            WHEN EXTRACT(EPOCH FROM (NOW() - ts)) < 86400 THEN '12-24h'
            ELSE '24h+'
        END as age_bucket,
        COUNT(*) as cnt
    FROM shadow_observations
    GROUP BY age_bucket
    ORDER BY MIN(EXTRACT(EPOCH FROM (NOW() - ts)))
""")
print(f"\nShadow observation age distribution:")
for r in age_dist:
    print(f"  {r['age_bucket']}: {r['cnt']}")

# Check: what is the resolution trigger in shadow.py?
print(f"\n  Resolution window (from shadow.py): 24 hours")
print(f"  Resolution trigger: ShadowComparator.resolve_pending() called in _tick()")
print(f"  Required age before resolution: 24 hours")

# Is the dashboard API available for resolution?
print(f"\n  Current time: {str(now)[:19]}")
print(f"  Oldest shadow obs age: calculated above")

# D: Pair Formation Logic
print("\n" + "=" * 70)
print("D: PAIR FORMATION LOGIC")
print("=" * 70)

# Trace the full pipeline
print("""
  Pipeline:
  1. Agent._tick() executes actions → records episodes
  2. ShadowComparator.observe() → shadow_observations (status=PENDING_24H)
  3. EpisodeResolver.resolve_pending_episodes() every tick → resolves episodes ≥ 6h old
     → agent_episodes.resolved=True
     → outcome_json filled with decision_quality, survival_score_delta, equity_delta
  4. ShadowComparator.resolve_pending() every tick → resolves shadow obs ≥ 24h old
     → shadow_observations.status='RESOLVED'
  5. MemoryMiner.mine_patterns() every 10th-50th tick → groups resolved episodes by
     (action_type, survival_mode, analyst_consensus, debate_verdict)
     → semantic_patterns
  6. PatternValidator.validate_patterns() → validates patterns by threshold checks
  7. RESOLVED PAIR: shadow_observation (RESOLVED) + memory_attribution
     linked via: shadow_observation.plan_id == memory_attribution.plan_id
""")

# Check memory_attribution presence
attr_counts = q("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN outcome_quality NOT IN ('pending') THEN 1 ELSE 0 END) as resolved_attr
    FROM memory_attributions
""")[0]
print(f"\n  Memory attributions: total={attr_counts['total']} resolved={attr_counts['resolved_attr']}")

# Check how many shadow obs have matching plan_ids in memory_attributions
pair_potential = q("""
    SELECT COUNT(DISTINCT so.id) as matching_shadows
    FROM shadow_observations so
    INNER JOIN memory_attributions ma ON ma.plan_id = so.plan_id
    WHERE so.status = 'PENDING_24H'
""")[0]
print(f"  Shadow obs with matching attribution plan_id (potential future pairs): {pair_potential['matching_shadows']}")

# Check how many shadow obs DON'T have matching attributions
no_attr_potential = q("""
    SELECT COUNT(*) as no_match
    FROM shadow_observations so
    WHERE so.status = 'PENDING_24H'
    AND NOT EXISTS (SELECT 1 FROM memory_attributions ma WHERE ma.plan_id = so.plan_id)
""")[0]
print(f"  Shadow obs WITHOUT matching attribution plan_id: {no_attr_potential['no_match']}")

# E: Check the episode resolution progress
print("\n" + "=" * 70)
print("E: RUNTIME BOTTLENECK ANALYSIS")
print("=" * 70)

# Episode resolver check: how many episodes are old enough but still unresolved?
old_unresolved = q("""
    SELECT COUNT(*) as count
    FROM agent_episodes
    WHERE resolved = False
    AND EXTRACT(EPOCH FROM (NOW() - ts)) > 21600  -- 6 hours
""")[0]
print(f"\n  Episodes > 6h old but still unresolved: {old_unresolved['count']}")

young_unresolved = q("""
    SELECT COUNT(*) as count
    FROM agent_episodes
    WHERE resolved = False
    AND EXTRACT(EPOCH FROM (NOW() - ts)) <= 21600
""")[0]
print(f"  Episodes <= 6h old and unresolved (too young): {young_unresolved['count']}")

# How many shadow obs old enough but not resolved?
old_shadow_pending = q("""
    SELECT COUNT(*) as count
    FROM shadow_observations
    WHERE status = 'PENDING_24H'
    AND EXTRACT(EPOCH FROM (NOW() - ts)) > 86400  -- 24 hours
""")[0]
print(f"\n  Shadow obs > 24h old but still PENDING_24H: {old_shadow_pending['count']}")

young_shadow_pending = q("""
    SELECT COUNT(*) as count
    FROM shadow_observations
    WHERE status = 'PENDING_24H'
    AND EXTRACT(EPOCH FROM (NOW() - ts)) <= 86400
""")[0]
print(f"  Shadow obs <= 24h old (not yet resolvable): {young_shadow_pending['count']}")

# Mining check: last episode ID processed by patterns
mining_checkpoint = q("SELECT MAX(last_episode_id_processed) as max_check FROM semantic_patterns")[0]
max_episode = q("SELECT MAX(id) as max_id FROM agent_episodes")[0]
print(f"\n  Pattern mining checkpoint (max episode processed): {mining_checkpoint['max_check']}")
print(f"  Latest episode ID in DB: {max_episode['max_id']}")
if max_episode['max_id'] and mining_checkpoint['max_check']:
    gap = max_episode['max_id'] - mining_checkpoint['max_check']
    print(f"  Mining gap (unprocessed episodes): {gap}")
    if gap > 0:
        print(f"  → Mining is BEHIND by {gap} episodes")

# Mining interval
print(f"\n  Mining interval: every 10 ticks (first 100 loops), then every 50 ticks")
print(f"  Agent loop interval: 300 seconds (5 minutes)")
print(f"  Ticks per day: ~288")
print(f"  Mining frequency: every ~50min (early), ~4.2h (after 100 loops)")

conn.close()