"""
Phase 8.2.3 — Shadow Performance Audit
Audit only. No code modifications.
"""
import os, sys, json, math
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from datetime import datetime, timezone

dsn = os.environ["AGENT_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()
now = datetime.now(timezone.utc)

def q(sql):
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

print("=" * 70)
print("PHASE 8.2.3 — SHADOW PERFORMANCE AUDIT")
print(f"Timestamp: {now.isoformat()}")
print("=" * 70)

# Find restart
plan_ts = q("SELECT ts FROM agent_plans ORDER BY ts")
plans = [p["ts"] for p in plan_ts]
restart_ts = None
for i in range(len(plans)-1, 0, -1):
    gap = (plans[i] - plans[i-1]).total_seconds() / 60
    if gap > 15:
        restart_ts = plans[i]
        break

# Check gate conditions first
shadow = q("SELECT * FROM shadow_memory_influence ORDER BY ts")
total_s = len(shadow)
attr = q("SELECT * FROM memory_attributions WHERE outcome_quality NOT IN ('pending','unknown')")
total_a = len(attr)

# Match pairs
sp = {s['plan_id']: s for s in shadow}
pairs = [(sp[a['plan_id']], a) for a in attr if a['plan_id'] in sp]

print(f"\nGATE CHECK: shadow={total_s}/25  resolved_pairs={len(pairs)}/10")
print(f"Required: >=25 shadow AND >=10 matched pairs")
print()

if total_s < 25 or len(pairs) < 10:
    print("INSUFFICIENT DATA — cannot produce meaningful audit yet.")
    needed_s = max(0, 25 - total_s)
    needed_p = max(0, 10 - len(pairs))
    print(f"Need {needed_s} more shadow evaluations and {needed_p} more matched pairs.")
    if total_s < 25:
        est = (25 - total_s) * 5
        print(f"Estimated runtime remaining: ~{est} min")
else:
    # A: Shadow Statistics
    print("\n--- A: SHADOW STATISTICS ---")
    print(f"Total: {total_s}")
    print(f"First: {shadow[0]['ts']}  Latest: {shadow[-1]['ts']}")
    for label, key in [("Action","memory_action"),("Survival mode","survival_mode"),("Debate verdict","debate_verdict")]:
        c = Counter(s.get(key,'?') for s in shadow)
        print(f"\nBy {label}: {dict(c)}")

    # B: Agreement Analysis
    print("\n--- B: AGREEMENT ANALYSIS ---")
    agree = sum(1 for s in shadow if s['agreement']=='AGREE')
    disagree = total_s - agree
    print(f"Agree: {agree} ({agree/total_s*100:.1f}%)")
    print(f"Disagree: {disagree} ({disagree/total_s*100:.1f}%)")
    print(f"SHADOW_ALIGNMENT_SCORE = {agree/total_s*100:.0f}/100")

    # C: Contribution Comparison
    print("\n--- C: CONTRIBUTION COMPARISON ---")
    for label, cond in [("AGREE", lambda s: s['agreement']=='AGREE'),
                         ("DISAGREE", lambda s: s['agreement']=='DISAGREE')]:
        matched = [(s,a) for s,a in pairs if cond(s)]
        if matched:
            avg_contrib = sum(float(a['memory_contribution_score']) for _,a in matched)/len(matched)
            avg_conf = sum(float(s['memory_confidence']) for s,_ in matched)/len(matched)
            avg_shadow = sum(float(s['shadow_influence_score']) for s,_ in matched)/len(matched)
            print(f"When {label}: avg_contrib={avg_contrib:.4f} avg_conf={avg_conf:.4f} avg_shadow={avg_shadow:.4f} n={len(matched)}")
    
    # D: Pattern Effectiveness
    print("\n--- D: PATTERN EFFECTIVENESS ---")
    patterns = q("SELECT * FROM semantic_patterns WHERE validated=TRUE")
    pat_stats = []
    for p in patterns:
        pid = p['id']
        used = sum(1 for s in shadow for x in (json.loads(s['pattern_ids_json']) if isinstance(s['pattern_ids_json'],str) else (s['pattern_ids_json'] or [])) if x == pid)
        if used:
            confs = [float(s['memory_confidence']) for s in shadow for x in (json.loads(s['pattern_ids_json']) if isinstance(s['pattern_ids_json'],str) else (s['pattern_ids_json'] or [])) if x == pid]
            scores = [float(s['shadow_influence_score']) for s in shadow for x in (json.loads(s['pattern_ids_json']) if isinstance(s['pattern_ids_json'],str) else (s['pattern_ids_json'] or [])) if x == pid]
            contribs = [float(a['memory_contribution_score']) for s,a in pairs for x in (json.loads(s['pattern_ids_json']) if isinstance(s['pattern_ids_json'],str) else (s['pattern_ids_json'] or [])) if x == pid]
            pat_stats.append({
                'pid': pid, 'key': p['pattern_key'], 'vs': p['validation_score'],
                'used': used, 'avg_conf': sum(confs)/len(confs),
                'avg_score': sum(scores)/len(scores),
                'avg_contrib': sum(contribs)/len(contribs) if contribs else 0
            })
    pat_stats.sort(key=lambda x: x['avg_contrib'], reverse=True)
    for ps in pat_stats:
        print(f"  P{ps['pid']}: {ps['key'][:40]:<40s} vs={ps['vs']:.4f} used={ps['used']} avg_conf={ps['avg_conf']:.4f} avg_contrib={ps['avg_contrib']:.4f}")
    if pat_stats:
        print(f"\nStrongest: {pat_stats[0]['key'][:40]} (contrib={pat_stats[0]['avg_contrib']:.4f})")
        print(f"Weakest:  {pat_stats[-1]['key'][:40]} (contrib={pat_stats[-1]['avg_contrib']:.4f})")

    # E: Controlled Influence Gate
    print("\n--- E: CONTROLLED INFLUENCE GATE ---")
    checks = {}
    checks["shadow >= 25"] = total_s >= 25
    checks["resolved pairs >= 10"] = len(pairs) >= 10
    checks["disagreement >= 10%"] = (disagree/total_s) >= 0.10 if total_s > 0 else False
    
    if pairs:
        agree_contrib = [float(a['memory_contribution_score']) for s,a in pairs if s['agreement']=='AGREE']
        disagree_contrib = [float(a['memory_contribution_score']) for s,a in pairs if s['agreement']=='DISAGREE']
        avg_a = sum(agree_contrib)/len(agree_contrib) if agree_contrib else 0
        avg_d = sum(disagree_contrib)/len(disagree_contrib) if disagree_contrib else 0
        checks["agree_contrib > disagree_contrib"] = avg_a > avg_d
        print(f"  agree_contrib={avg_a:.4f} vs disagree_contrib={avg_d:.4f} -> {'✅' if avg_a>avg_d else '❌'}")
    
    # Pattern dominance
    if shadow:
        usage_counts = {}
        for p in q("SELECT * FROM semantic_patterns WHERE validated=TRUE"):
            pid = p['id']
            usage_counts[pid] = sum(1 for s in shadow for x in (json.loads(s['pattern_ids_json']) if isinstance(s['pattern_ids_json'],str) else (s['pattern_ids_json'] or [])) if x == pid)
        if usage_counts:
            max_share = max(usage_counts.values())/max(1,sum(usage_counts.values()))
            checks["no pattern > 80%"] = max_share <= 0.80
            print(f"  max pattern share: {max_share*100:.0f}% {'✅' if max_share<=0.80 else '❌'}")

    for k,v in checks.items():
        print(f"  {k:40s}: {'PASS' if v else 'FAIL'}")
    
    ready = all(checks.values())
    print(f"\nCONTROLLED_WEIGHT_005_READY = {'TRUE' if ready else 'FALSE'}")
    if not ready:
        print("Blockers:", [k for k,v in checks.items() if not v])

    # F: Recommendation
    print("\n--- F: RECOMMENDATION ---")
    if ready:
        print("RECOMMENDATION: ENABLE_WEIGHT_0_05")
        print("Justification: All gates passed — memory demonstrates measurable signal.")
    elif total_s >= 10:
        print("RECOMMENDATION: CONTINUE_SHADOW_ONLY")
        print("Justification: Not all gates passed yet.")
    else:
        print("RECOMMENDATION: CONTINUE_SHADOW_ONLY")
        print("Justification: Insufficient data.")

conn.close()
print("\nAudit complete. No code changes made.")