"""Quick helper to list tables (and row counts) of a SQLite DB.

Usage (PowerShell from repo root or any subfolder):
  py backend\data\inspect-db.py              # Inspect backend app DB
  py backend\data\inspect-db.py tradesv3.dryrun.sqlite   # Inspect Freqtrade runtime DB
  py backend\data\inspect-db.py path\to\other.db        # Custom path

Adds defensive checks to avoid the 'sqlite3.OperationalError: unable to open database file'.
"""

from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

def resolve_default_backend_db(script_path: Path) -> Path:
    # script_path = .../backend/data/inspect-db.py
    # repo_root = parents[2]
    repo_root = script_path.resolve().parents[2]
    return repo_root / "backend" / "app" / "data" / "backend.db"

def resolve_freqtrade_db(script_path: Path) -> Path:
    repo_root = script_path.resolve().parents[2]
    return repo_root / "tradesv3.dryrun.sqlite"

def main(argv: list[str]):
    script_path = Path(__file__)
    # Simple flags
    include_views = any(a.lower() in {"--include-views", "--views"} for a in argv[1:])
    dump_schema = any(a.lower() in {"--schema", "-s"} for a in argv[1:])

    # Find first non-flag argument as DB path
    arg_path = None
    for a in argv[1:]:
        if not a.startswith("-"):
            arg_path = a
            break

    if arg_path:
        # User supplied a path
        supplied = Path(arg_path)
        if not supplied.is_absolute():
            supplied = Path.cwd() / supplied
        target = supplied
    else:
        # Prefer backend app DB; if it doesn't exist yet, fall back to freqtrade one
        backend_db = resolve_default_backend_db(script_path)
        freqtrade_db = resolve_freqtrade_db(script_path)
        if backend_db.exists():
            target = backend_db
        elif freqtrade_db.exists():
            target = freqtrade_db
        else:
            print("ERROR: Neither backend app DB nor Freqtrade DB found.")
            print(f"Expected backend: {backend_db}")
            print(f"Expected freqtrade: {freqtrade_db}")
            print("If the bot hasn't started yet, start it once to create the DB, or pass a custom path.")
            return 2

    if not target.exists():
        print(f"ERROR: Database file does not exist: {target}")
        parent = target.parent
        print("Parent directory exists:" , parent.exists(), "->", parent)
        if parent.exists():
            print("Directory contents:")
            for p in sorted(parent.iterdir()):
                print("  ", p.name)
        return 1

    # Open read-only using URI for safety
    try:
        uri = f"file:{target.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as e:
        print(f"ERROR: Could not open database: {target}\n{e}")
        print("Common causes: wrong path, locked directory permissions, or path contains characters requiring escaping.")
        return 3

    print(f"Opened: {target}")
    print("SQLite version:", sqlite3.sqlite_version)

    cursor = conn.cursor()
    # Collect tables (and optionally views)
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")] \
        if True else []
    views = []
    if include_views:
        views = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")] \
            if True else []
    if not tables:
        print("(No tables found)")
    else:
        width = max(len(t) for t in tables)
        print("Tables (with row counts):")
        for t in tables:
            try:
                (cnt,) = cursor.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()
            except Exception as e:  # noqa: BLE001
                cnt = f"ERR: {e}"  # pragma: no cover
            print(f"  {t.ljust(width)}  {cnt}")

    if views:
        print("\nViews:")
        for v in views:
            print(f"  {v}")

    # Optional: show the first few rows of core tables
    sample_tables = [name for name in ("trades", "orders", "pairlocks") if name in tables]
    for t in sample_tables:
        print(f"\nFirst 5 rows of {t}:")
        try:
            rows = cursor.execute(f"SELECT * FROM '{t}' LIMIT 5").fetchall()
            if not rows:
                print("  (empty)")
            else:
                for r in rows:
                    print("  ", r)
        except Exception as e:  # noqa: BLE001
            print("  Error reading table:", e)

    # Dump schemas if requested
    if dump_schema:
        print("\nSchemas (CREATE statements):")
        try:
            rows = cursor.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()
            for typ, name, sql in rows:
                print(f"\n-- {typ}: {name}\n{sql}")
        except Exception as e:
            print("  Error reading schemas:", e)

    conn.close()
    return 0


def list_tables(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(main(sys.argv))
