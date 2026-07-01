"""
Apply scanner configuration migration
Run this script to add scanner_configs table and update market_snapshots
"""
import sqlite3
from pathlib import Path

# Path to database
DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"
MIGRATION_SQL = Path(__file__).parent / "migrations" / "add_scanner_configs.sql"

def run_migration():
    print(f"Applying scanner configs migration to: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"Database does not exist yet. Will be created on first run.")
        return
    
    if not MIGRATION_SQL.exists():
        print(f"Migration file not found: {MIGRATION_SQL}")
        return
    
    # Read migration SQL
    with open(MIGRATION_SQL, "r", encoding="utf-8") as f:
        sql = f.read()
    
    # Apply migration
    conn = sqlite3.connect(DB_PATH)
    try:
        # Split into individual statements
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
        
        for statement in statements:
            try:
                conn.execute(statement)
                print(f"✓ Executed: {statement[:60]}...")
            except sqlite3.OperationalError as e:
                if "already exists" in str(e) or "duplicate column" in str(e):
                    print(f"⊘ Skipped (already exists): {statement[:60]}...")
                else:
                    print(f"✗ Error: {e}")
                    print(f"  Statement: {statement[:100]}...")
        
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
