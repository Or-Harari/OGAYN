"""Check for temporary tables and complete migration"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "data" / "backend.db"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=== All tables ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
for row in cursor.fetchall():
    print(row[0])

# Check if the new tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_new';")
new_tables = [row[0] for row in cursor.fetchall()]

if new_tables:
    print(f"\n=== Found temporary tables: {new_tables} ===")
    
    # Complete the migration
    if 'market_snapshots_new' in new_tables:
        print("\nDropping old market_snapshots and renaming new one...")
        cursor.execute("DROP TABLE IF EXISTS market_snapshots;")
        cursor.execute("ALTER TABLE market_snapshots_new RENAME TO market_snapshots;")
        
        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_scanner ON market_snapshots(scanner_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_user ON market_snapshots(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol ON market_snapshots(symbol);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_timestamp ON market_snapshots(timestamp);")
        print("✓ market_snapshots migration complete")
    
    if 'market_data_cache_new' in new_tables:
        print("\nDropping old market_data_cache and renaming new one...")
        cursor.execute("DROP TABLE IF EXISTS market_data_cache;")
        cursor.execute("ALTER TABLE market_data_cache_new RENAME TO market_data_cache;")
        print("✓ market_data_cache migration complete")
    
    conn.commit()
    print("\n=== Migration complete! ===")
else:
    print("\nNo temporary tables found - migration may have already completed or not started yet")

conn.close()
