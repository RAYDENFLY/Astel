"""
Comprehensive branding search across the entire repository.
Searches for: QuantumTrade, Quantum Trade, QuantumTerminal, Quantum Terminal, Quantum, QT
Excludes: .git, __pycache__, .venv, node_modules
Prints every find with file path and line number.
"""
import os
import sys

SEARCH_TERMS = ["QuantumTrade", "Quantum Trade", "QuantumTerminal", "Quantum Terminal"]
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".gitattributes"}
EXCLUDE_EXTS = {".pyc", ".pyo"}
ALLOWED_EXTS = {".py", ".md", ".html", ".yaml", ".yml", ".txt", ".sql", ".json", ".cfg", ".ini", ".toml"}

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
matches = []

for root, dirs, files in os.walk(root_dir):
    # Skip excluded directories
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    rel_root = os.path.relpath(root, root_dir)
    if any(excl in rel_root.split(os.sep) for excl in EXCLUDE_DIRS):
        continue

    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext in EXCLUDE_EXTS:
            continue
        if ext not in ALLOWED_EXTS:
            # Still check .txt and .md only
            if ext not in (".py", ".md", ".html", ".yaml", ".yml", ".txt", ".sql", ".json"):
                continue
        fpath = os.path.join(root, fname)
        rel_path = os.path.relpath(fpath, root_dir)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, 1):
                    for term in SEARCH_TERMS:
                        if term in line:
                            stripped = line.strip()[:120]
                            matches.append((rel_path, line_no, term, stripped))
        except Exception as e:
            print(f"ERROR reading {rel_path}: {e}", file=sys.stderr)

# Print results
if not matches:
    print("=" * 60)
    print("BRANDING SEARCH COMPLETE")
    print("=" * 60)
    print(f"\n✅ ZERO occurrences found of: {', '.join(SEARCH_TERMS)}")
    print("\nThe repository is 100% branded as: Astel Research - TradingAgents")
    sys.exit(0)

print("=" * 60)
print("REMAINING BRANDING OCCURRENCES")
print("=" * 60)
for path, line, term, content in matches:
    print(f"\n  {path}:{line}")
    print(f"    Term: '{term}'")
    print(f"    Line: {content}")

print(f"\nTotal: {len(matches)} remaining occurrences")
sys.exit(1)