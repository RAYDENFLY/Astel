"""Phase 8 Monitoring Watch — monitors thresholds and triggers audit."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

# 1. Shadow evaluations
cur.execute("SELECT COUNT(*) FROM shadow_memory_influence")
s = int(cur.fetchone()[0])

# 2. Resolved shadow-attribution pairs
cur.execute("""
    SELECT COUNT(*) FROM memory_attributions a
    INNER JOIN shadow_memory_influence si ON a.plan_id = si.plan_id
    WHERE a.outcome_quality NOT IN ('pending', 'unknown')
""")
pairs = int(cur.fetchone()[0])

# 3. Validated patterns
cur.execute("SELECT COUNT(*) FROM semantic_patterns WHERE validated=TRUE")
vp = int(cur.fetchone()[0])

# 4. Agreement/disagreement
cur.execute("SELECT COUNT(*) FROM shadow_memory_influence WHERE agreement='AGREE'")
agree = int(cur.fetchone()[0])
total = s
disagree = total - agree

print("SHADOW: %d/25 (%d%%)" % (s, min(100, s*100//25)))
print("PAIRS:  %d/10 (%d%%)" % (pairs, min(100, pairs*100//10)))
print("PATS:   %d/3 (%d%%)" % (vp, min(100, vp*100//3)))
print("AGREE:  %d/%d (%d%%)" % (agree, total, agree*100//max(1,total)))
print("DISAG:  %d/%d (%d%%)" % (disagree, total, disagree*100//max(1,total)))

if s >= 25 and pairs >= 10 and vp >= 3:
    print("\nALL_THRESHOLDS_MET: Trigger Phase 8.3 Controlled Influence Readiness Audit")
    # Run the Phase 8.3 audit
    audit_path = os.path.join(os.path.dirname(__file__), "_phase823_audit.py")
    if os.path.exists(audit_path):
        exec(open(audit_path).read())
else:
    print("\nWAITING_FOR_DATA")
    missing = []
    if s < 25:
        missing.append("%d more shadow evals (~%dmin)" % (25-s, (25-s)*5))
    if pairs < 10:
        missing.append("%d more resolved pairs (~6h from restart)" % (10-pairs))
    if vp < 3:
        missing.append("%d more validated patterns" % (3-vp))
    print("Missing:", " | ".join(missing))

conn.close()