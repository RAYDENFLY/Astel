"""Verify agent data was generated correctly."""
import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Check SQLite (agent was writing here without .env loaded)
con = sqlite3.connect('agent/agent.sqlite')
con.row_factory = sqlite3.Row

rows = con.execute('SELECT id, ts, plan_json, input_snapshot FROM agent_plans ORDER BY ts').fetchall()
print("=== PLANS ===")
print(f"Total: {len(rows)}")
for r in rows:
    inp = json.loads(r['input_snapshot']) if r['input_snapshot'] else {}
    plan = json.loads(r['plan_json']) if r['plan_json'] else {}
    print(f"  #{r['id']}: ts={r['ts'][:19]} summary={plan.get('summary','')[:40]}")
    print(f"       treasury={inp.get('treasury_usdt', 'MISSING')} survival={inp.get('survival_mode','MISSING')}")
    print(f"       account_equity={inp.get('account',{}).get('equity','MISSING')} drawdown={inp.get('account',{}).get('drawdown_pct','MISSING')}")

rows = con.execute('SELECT count(*) FROM agent_actions').fetchone()
print(f"\n=== ACTIONS ===")
print(f"Total: {rows[0]}")

rows = con.execute('SELECT count(*) FROM agent_treasury').fetchone()
print(f"\n=== TREASURY ===")
print(f"Total: {rows[0]}")

rows = con.execute('SELECT id, ts, recommended_action, agreement FROM shadow_observations ORDER BY ts').fetchall()
print(f"\n=== SHADOW OBSERVATIONS ===")
print(f"Total: {len(rows)}")
for r in rows:
    print(f"  #{r['id']}: ts={r['ts'][:19]} action={r['recommended_action']} agreement={r['agreement']}")