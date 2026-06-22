import os, sys, json, psycopg2
from dotenv import load_dotenv; load_dotenv()
dsn = os.environ['AGENT_POSTGRES_DSN']
conn = psycopg2.connect(dsn); cur = conn.cursor()

print("TABLES IN DATABASE:")
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
for r in cur.fetchall(): print(f"  {r[0]}")

print("\nALL PATTERNS:")
cur.execute("SELECT id, pattern_key, sample_size, confidence_score, validation_score, validated, active, first_seen FROM semantic_patterns ORDER BY sample_size DESC")
for r in cur.fetchall(): print(f"  id={r[0]} key={r[1][:60]} sample={r[2]} conf={r[3]} val_score={r[4]} validated={r[5]} active={r[6]} first={str(r[7])[:19]}")

print("\nEPISODE VERDICT DISTRIBUTION:")
cur.execute("SELECT action_type, survival_mode, analyst_consensus, debate_verdict, COUNT(*) as cnt FROM agent_episodes GROUP BY action_type, survival_mode, analyst_consensus, debate_verdict ORDER BY cnt DESC")
for r in cur.fetchall(): print(f"  {str(r[0]):25s} {str(r[1]):15s} {str(r[2]):15s} {str(r[3]):12s}: {r[4]}")

print("\nSHADOW MEMORY INFLUENCE - debate_verdict distribution:")
cur.execute("SELECT debate_verdict, COUNT(*) as cnt FROM shadow_memory_influence GROUP BY debate_verdict ORDER BY cnt DESC")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

print("\nQ: Are there ANY episodes with analyst_consensus='bearish'?")
cur.execute("SELECT COUNT(*) as cnt FROM agent_episodes WHERE analyst_consensus = 'bearish'")
print(f"  count: {cur.fetchone()[0]}")

print("\nQ: What are all distinct analyst_consensus values?")
cur.execute("SELECT analyst_consensus, COUNT(*) as cnt FROM agent_episodes GROUP BY analyst_consensus ORDER BY cnt DESC")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

print("\nQ: Episodes with debate_verdict = 'bearish'?")
cur.execute("SELECT debate_verdict, COUNT(*) as cnt FROM agent_episodes GROUP BY debate_verdict ORDER BY cnt DESC")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

print("\nQ: Shadow observations - why 0 resolved?")
cur.execute("SELECT status, COUNT(*) as cnt FROM shadow_observations GROUP BY status ORDER BY cnt DESC")
for r in cur.fetchall(): print(f"  status={r[0]}: {r[1]}")

print("\nQ: Latest 5 shadow observations sample:")
cur.execute("SELECT id, plan_id, ts, status, agreement FROM shadow_observations ORDER BY ts DESC LIMIT 5")
for r in cur.fetchall(): print(f"  id={r[0]} plan={r[1]} ts={str(r[2])[:19]} status={r[3]} agreement={r[4]}")

print("\nQ: Do resolved episodes have outcome_json with debate_verdict?")
cur.execute("SELECT id, outcome_json::text as ojt FROM agent_episodes WHERE resolved=True AND outcome_json::text LIKE '%debate_verdict%' LIMIT 3")
rows = cur.fetchall()
print(f"  count: {len(rows)}")
for r in rows: print(f"  ep={r[0]} json={r[1][:200]}")

print("\nQ: Episodes that are resolved=true + debate_verdict='unknown' count:")
cur.execute("SELECT COUNT(*) as cnt FROM agent_episodes WHERE resolved=True AND debate_verdict='unknown'")
print(f"  count: {cur.fetchone()[0]}")

conn.close()