"""
Fixes the misplaced storage methods and implements them in both classes.
"""
content = open("agent/storage.py", encoding="utf-8").read()

# Remove the floating methods block between PG_SCHEMA and SQLiteAgentStorage
# It's between line 674 (after SQLITE_SCHEMA end """) and line 718 (class SQLiteAgentStorage)
sqlite_start = content.find("class SQLiteAgentStorage(AgentStorage):")
pg_schema_end = content.rfind('"""', 0, sqlite_start)

# Find what's between SQLITE_SCHEMA end and SQLiteAgentStorage
between = content[pg_schema_end + 3:sqlite_start]
if "def save_reasoning_audit" in between:
    # Remove the floating methods
    content = content[:pg_schema_end + 3] + "\n\n" + content[sqlite_start:]
    print("Removed floating methods block")

# Now find the last method of PostgresAgentStorage and add methods before class ends
pg_end_marker = 'log.exception("get_shadow_memory_influence_metrics failed")'
pg_end_pos = content.find(pg_end_marker, content.find("class PostgresAgentStorage"))
if pg_end_pos > 0:
    # Find the end of this method - the next line after except block before next class
    end_of_pg = content.find("class SQLiteAgentStorage", pg_end_pos)
    pg_methods = """
    # Phase 9.2 — Reasoning audit
    def save_reasoning_audit(self, plan_id, llm_provider, memory_usage_score, ml_used, procedural_used, episodic_used, shadow_used, portfolio_used, risk_used, treasury_used, reasoning_json, context_size_chars=0, latency_ms=0.0, raw_content_length=0) -> None:
        with self._get_conn().cursor() as cur:
            cur.execute("INSERT INTO agent_reasoning_audit (plan_id, llm_provider, memory_usage_score, ml_used, procedural_used, episodic_used, shadow_used, portfolio_used, risk_used, treasury_used, reasoning_json, context_size_chars, latency_ms, raw_content_length) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (plan_id, llm_provider, memory_usage_score, ml_used, procedural_used, episodic_used, shadow_used, portfolio_used, risk_used, treasury_used, reasoning_json, context_size_chars, latency_ms, raw_content_length))

    def get_reasoning_audits(self, limit=20) -> List[Dict[str, Any]]:
        try:
            with self._get_conn().cursor() as cur:
                cur.execute("SELECT * FROM agent_reasoning_audit ORDER BY created_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, r)) for r in rows]
        except Exception:
            log.exception("get_reasoning_audits failed")
            return []

    def get_reasoning_audit_summary(self) -> Dict[str, Any]:
        try:
            with self._get_conn().cursor() as cur:
                cur.execute("SELECT COUNT(*) as total, COALESCE(AVG(memory_usage_score),0) as avg_score, SUM(CASE WHEN ml_used=TRUE THEN 1 ELSE 0 END) as ml, SUM(CASE WHEN procedural_used=TRUE THEN 1 ELSE 0 END) as proc, SUM(CASE WHEN episodic_used=TRUE THEN 1 ELSE 0 END) as epi, SUM(CASE WHEN shadow_used=TRUE THEN 1 ELSE 0 END) as shad, SUM(CASE WHEN portfolio_used=TRUE THEN 1 ELSE 0 END) as port, SUM(CASE WHEN risk_used=TRUE THEN 1 ELSE 0 END) as risk, SUM(CASE WHEN treasury_used=TRUE THEN 1 ELSE 0 END) as treas FROM agent_reasoning_audit")
                row = cur.fetchone()
                total = int(row[0]) if row else 0
                return {
                    "total_audits": total,
                    "avg_memory_usage_score": round(float(row[1] or 0), 2) if row else 0.0,
                    "ml_usage_rate": round(int(row[2] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "procedural_usage_rate": round(int(row[3] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "episodic_usage_rate": round(int(row[4] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "shadow_usage_rate": round(int(row[5] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "portfolio_usage_rate": round(int(row[6] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "risk_usage_rate": round(int(row[7] or 0) / max(1, total), 2) if total > 0 else 0.0,
                    "treasury_usage_rate": round(int(row[8] or 0) / max(1, total), 2) if total > 0 else 0.0,
                }
        except Exception:
            log.exception("get_reasoning_audit_summary failed")
            return {"total_audits": 0, "avg_memory_usage_score": 0.0}

    # Phase 9.3 — Reasoning feedback
    def save_reasoning_feedback(self, plan_id, reflection, missing_dimensions, recommended_improvements, severity="info") -> None:
        try:
            with self._get_conn().cursor() as cur:
                cur.execute("INSERT INTO agent_reasoning_feedback (plan_id, reflection, missing_dimensions, recommended_improvements, severity) VALUES (%s,%s,%s,%s,%s)", (plan_id, reflection, missing_dimensions, recommended_improvements, severity))
        except Exception:
            log.exception("save_reasoning_feedback failed")
"""
    # Insert before SQLiteAgentStorage class
    content = content.replace(
        "class SQLiteAgentStorage(AgentStorage):",
        pg_methods + "\n\nclass SQLiteAgentStorage(AgentStorage):"
    )
    print("Added methods to PostgresAgentStorage")

open("agent/storage.py", "w", encoding="utf-8").write(content)
print("Done")