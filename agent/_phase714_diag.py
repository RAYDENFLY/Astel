"""Diagnose why MemoryMiner returns 0 patterns despite 11 qualifying episodes."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

print("=== MEMORYMINER MANUAL DIAGNOSTIC ===")

# 1. Get recent episodes exactly as MemoryMiner does
cur.execute("SELECT * FROM agent_episodes ORDER BY ts DESC LIMIT 500")
cols = [desc[0] for desc in cur.description]
all_eps = [dict(zip(cols, row)) for row in cur.fetchall()]
print(f"Total episodes from get_recent_episodes: {len(all_eps)}")

# 2. Filter resolved - exactly as MemoryMiner line 56
resolved = [ep for ep in all_eps if ep.get("resolved") is True or ep.get("resolved") == 1]
print(f"Resolved episodes (with 'is True or == 1'): {len(resolved)}")

# Debug: print resolved values for first 20
for ep in all_eps[:20]:
    r = ep.get("resolved")
    print(f"  ep={ep.get('id')} resolved={r} type={type(r).__name__}")

# 3. If resolved count is wrong, show the issue
if len(resolved) < 5:
    print(f"\n*** BUG: Only {len(resolved)} resolved episodes detected!")
    # Count what PG says
    cur.execute("SELECT COUNT(*) FROM agent_episodes WHERE resolved = true")
    pg_true = cur.fetchone()[0]
    print(f"PG count resolved=true: {pg_true}")
    
    # Check the actual values
    cur.execute("SELECT id, resolved FROM agent_episodes ORDER BY id")
    for r in cur.fetchall():
        print(f"  ep={r[0]} resolved={r[1]} (data type from PG)")

# 4. Group episodes (same as mine_patterns)
if len(resolved) >= 5:
    from collections import Counter
    groups = Counter(
        (ep.get("action_type","?"), ep.get("survival_mode","?"), 
         ep.get("analyst_consensus","?"), ep.get("debate_verdict","?"))
        for ep in resolved
    )
    print(f"\nGroups found: {len(groups)}")
    for key, cnt in groups.most_common():
        # Check if success_rate passes filter
        print(f"  {key}: {cnt} eps {'PASS' if cnt >= 5 else 'FAIL (need >= 5)'}")

# 5. Test direct MemoryMiner import
print(f"\n=== Testing direct import ===")
sys.path.insert(0, os.path.dirname(__file__))
from agent.memory_miner import MemoryMiner
from agent.storage import make_storage

storage = make_storage()
storage.init_schema()
miner = MemoryMiner(storage)
result = miner.mine_patterns()
print(f"MemoryMiner.mine_patterns() returned: {result}")

# Check patterns now
cur.execute("SELECT COUNT(*) FROM semantic_patterns")
print(f"Patterns after mining: {cur.fetchone()[0]}")

# Check for any error logs in the database (if stored)
cur.execute("SELECT id, pattern_key, sample_size, success_rate, confidence_score FROM semantic_patterns")
for r in cur.fetchall():
    print(f"  Pattern: {r}")

conn.close()
print("\nDiagnostic complete.")