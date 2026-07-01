"""Check database schema after migration"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "data" / "backend.db"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=== market_snapshots schema ===")
cursor.execute("PRAGMA table_info(market_snapshots);")
for row in cursor.fetchall():
    print(f"{row[1]}: {row[2]}, NOT NULL={row[3]}")

print("\n=== market_data_cache schema ===")
cursor.execute("PRAGMA table_info(market_data_cache);")
for row in cursor.fetchall():
    print(f"{row[1]}: {row[2]}, NOT NULL={row[3]}")

conn.close()
