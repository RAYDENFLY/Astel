"""Reset SQLite journal DB (trades, closures, equity, weekly stats, runner state).

Use when you manually close positions and want a clean journal.

Safety:
- Creates a timestamped backup copy next to the DB before deleting.
- Re-initializes schema + additive migrations.

Run:
  python scripts/reset_journal_db.py

Optional:
  python scripts/reset_journal_db.py --no-backup
  python scripts/reset_journal_db.py --db quant_system/database/quant_system.sqlite
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_system.database.db import Database




def _load_cfg() -> dict:
    cfg_path = ROOT / "quant_system" / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("Invalid config")
    return cfg


def reset_db(*, db_path: Path, schema_path: Path, backup: bool) -> None:
    db_path = db_path.resolve()
    schema_path = schema_path.resolve()

    if db_path.exists() and backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.with_suffix(db_path.suffix + f".bak_{ts}")
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_path}")

    if db_path.exists():
        db_path.unlink()
        print(f"Deleted: {db_path}")

    db = Database(db_path=db_path, schema_path=schema_path)
    db.initialize()
    print("Re-initialized schema + migrations")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="DB path (relative to repo root) override")
    ap.add_argument("--no-backup", action="store_true", help="Do not create a backup")
    args = ap.parse_args()

    cfg = _load_cfg()
    paths = cfg.get("paths") or {}

    rel_db = args.db or paths.get("db_path", "quant_system/database/quant_system.sqlite")
    rel_schema = paths.get("schema_path", "quant_system/database/schema.sql")

    reset_db(
        db_path=(ROOT / rel_db),
        schema_path=(ROOT / rel_schema),
        backup=not args.no_backup,
    )


if __name__ == "__main__":
    main()
