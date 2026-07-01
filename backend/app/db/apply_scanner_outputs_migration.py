"""
Apply scanner outputs migration
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"
MIGRATION_SQL = Path(__file__).parent / "migrations" / "add_scanner_outputs.sql"

def run_migration():
    print(f"Applying scanner outputs migration to: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"Database does not exist yet.")
        return
    
    if not MIGRATION_SQL.exists():
        print(f"Migration file not found: {MIGRATION_SQL}")
        return
    
    # Read migration SQL
    with open(MIGRATION_SQL, "r", encoding="utf-8") as f:
        sql = f.read()
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # Split into individual statements
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
        
        for statement in statements:
            try:
                conn.execute(statement)
                # Truncate for display
                display = statement[:80].replace("\n", " ")
                print(f"✓ Executed: {display}...")
            except sqlite3.OperationalError as e:
                if "already exists" in str(e) or "duplicate column" in str(e):
                    display = statement[:80].replace("\n", " ")
                    print(f"⊘ Skipped: {display}...")
                else:
                    print(f"✗ Error: {e}")
        
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
