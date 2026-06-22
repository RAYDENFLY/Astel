"""
Phase 8.2.10 — Debate Verdict Lineage Audit
Uses live PostgreSQL. No code changes. Audit only.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from collections import Counter

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
print("PHASE 8.2.10 — DEBATE VERDICT LINEAGE AUDIT")
print("=" * 70)

# A: Verdict Storage Locations
print("\n--- A: VERDICT STORAGE LOCATIONS ---")
for table, col in [
    ("agent_episodes", "debate_verdict"),
    ("memory_attributions", "debate_verdict"),
    ("shadow_memory_influence", "debate_verdict"),
]:
    rows = q("SELECT %s as v, COUNT(*) as c FROM %s GROUP BY %s ORDER BY COUNT(*) DESC" % (col, table, col))
    print(f"\n{table}.{col}:")
    for r in rows:
        print(f"  {r['v']:<20s}: {r['c']}")

# Also check outcome_json for debate verdicts
print("\nagent_episodes.outcome_json: parsing for debate_verdict keys...")
rows = q("SELECT outcome_json FROM agent_episodes ORDER BY ts DESC LIMIT 200")
verdicts_in_json = Counter()
for r in rows:
    o = r['outcome_json']
    if isinstance(o, str):
        try: o = json.loads(o)
        except: o = {}
    if isinstance(o, dict):
        dv = o.get('debate_verdict')
        if dv:
            verdicts_in_json[str(dv)] += 1
print(f"  Found in outcome_json: {dict(verdicts_in_json)}")

# B: Lineage Consistency
print("\n--- B: LINEAGE CONSISTENCY (last 100 episodes) ---")
eps = q("""SELECT e.id, e.debate_verdict as ep_verdict, e.outcome_json,
                  a.debate_verdict as attr_verdict,
                  s.debate_verdict as shadow_verdict
           FROM agent_episodes e
           LEFT JOIN memory_attributions a ON a.episode_id = e.id
           LEFT JOIN shadow_memory_influence s ON s.plan_id = e.plan_id
           ORDER BY e.ts DESC LIMIT 100""")
mismatches = 0
for e in eps:
    ep_id = e['id']
    ep_v = e.get('ep_verdict','?')
    attr_v = e.get('attr_verdict')
    shadow_v = e.get('shadow_verdict')
    ojson = e.get('outcome_json','{}')
    if isinstance(ojson, str):
        try: ojson_d = json.loads(ojson)
        except: ojson_d = {}
    else: ojson_d = ojson or {}
    ojson_v = ojson_d.get('debate_verdict')
    
    # Check consistency between episode.debate_verdict and outcome_json.debate_verdict
    if ojson_v and ojson_v != ep_v:
        print(f"  MISMATCH ep={ep_id}: debate_verdict='{ep_v}' vs outcome_json='{ojson_v}'")
        mismatches += 1
    
    # Check attribution matches episode
    if attr_v and attr_v != ep_v and ep_v != 'unknown':
        print(f"  MISMATCH ep={ep_id}: episode='{ep_v}' vs attribution='{attr_v}'")
        mismatches += 1

print(f"  Total mismatches found: {mismatches}")
print(f"  LINEAGE_HEALTH: {'GOOD' if mismatches == 0 else 'WARNING (' + str(mismatches) + ' mismatches)'}")

# C: Bearish Episode Investigation
print("\n--- C: BEARISH EPISODE INVESTIGATION ---")
# Query ALL distinct debate_verdict values
cur.execute("SELECT DISTINCT debate_verdict FROM agent_episodes")
print("All distinct debate_verdict values in agent_episodes:")
for r in cur.fetchall():
    print(f"  '{r[0]}'")

# Search outcome_json for 'bearish'
cur.execute("""
    SELECT id, ts, debate_verdict, outcome_json, action_type, survival_mode
    FROM agent_episodes
    WHERE outcome_json::text LIKE '%bearish%'
    ORDER BY ts DESC LIMIT 20
""")
rows = cur.fetchall()
print(f"\nEpisodes with 'bearish' in outcome_json: {len(rows)}")
for r in rows:
    o = r[3]
    if isinstance(o, str):
        try: o = json.loads(o)
        except: o = {}
    dv = o.get('debate_verdict', 'NOT FOUND') if isinstance(o, dict) else 'PARSE_ERROR'
    print(f"  ep={r[0]} at={r[1]} ep_verdict={r[2]} outcome_json.verdict={dv} action={r[4]} mode={r[5]}")

# Search for bearish in ALL text columns
cur.execute("""
    SELECT id, ts, debate_verdict, action_type, survival_mode, outcome_json::text as ojt
    FROM agent_episodes
    WHERE debate_verdict = 'bearish' OR outcome_json::text LIKE '%bearish%'
    ORDER BY ts DESC LIMIT 20
""")
rows = cur.fetchall()
print(f"\nAny episode with bearish anywhere: {len(rows)}")
for r in rows:
    print(f"  ep={r[0]} verdict={r[1]} action={r[3]} mode={r[4]} json_preview={r[5][:150]}")

# Check memory_attributions for bearish
cur.execute("SELECT COUNT(*) FROM memory_attributions WHERE debate_verdict = 'bearish'")
bc = cur.fetchone()[0]
print(f"\nmemory_attributions with bearish: {bc}")

# Check shadow_memory_influence for bearish
cur.execute("SELECT COUNT(*) FROM shadow_memory_influence WHERE debate_verdict = 'bearish'")
bc2 = cur.fetchone()[0]
print(f"shadow_memory_influence with bearish: {bc2}")

# The 32 bearish claim investigation
print("\n--- INVESTIGATING PREVIOUS CLAIM OF 32 BEARISH EPISODES ---")
print("Previous audit (8.2.6) reported TIGHTEN_RISK|CONSERVATIVE|bearish|unknown with 32 eps.")
print("That query used: SELECT action_type, survival_mode, analyst_consensus, debate_verdict")
print("                FROM agent_episodes")
print("                WHERE CAST(resolved AS integer)=1")
print()
print("Re-running that exact query pattern:")
cur.execute("""
    SELECT action_type, survival_mode, analyst_consensus, debate_verdict, COUNT(*)
    FROM agent_episodes
    GROUP BY 1,2,3,4
    ORDER BY COUNT(*) DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]:<25s} {r[1]:<15s} {r[2]:<15s} {r[3]:<12s}: {r[4]}")

# Check ALL episodes (not just resolved) for bearish
print("\nALL episodes (including unresolved) by debate_verdict:")
cur.execute("""
    SELECT debate_verdict, COUNT(*) as cnt,
           SUM(CASE WHEN CAST(resolved AS integer)=1 THEN 1 ELSE 0 END) as resolved
    FROM agent_episodes
    GROUP BY debate_verdict
    ORDER BY cnt DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]:<20s}: total={r[1]} resolved={r[2]}")

conn.close()
print("\nAudit complete. No code changes made.")