"""
Add database indexes for scanner performance
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"

def add_indexes():
    print(f"Adding performance indexes to: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Add composite index for scanner queries
        print("Creating index: idx_scanner_timestamp...")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scanner_timestamp 
            ON market_snapshots(scanner_id, timestamp DESC)
        ''')
        
        # Add composite index for scanner + quality filtering
        print("Creating index: idx_scanner_quality...")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scanner_quality 
            ON market_snapshots(scanner_id, market_quality DESC, timestamp DESC)
        ''')
        
        # Add composite index for symbol lookups
        print("Creating index: idx_scanner_symbol...")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scanner_symbol 
            ON market_snapshots(scanner_id, symbol, timestamp DESC)
        ''')
        
        conn.commit()
        
        # Analyze to update query planner statistics
        print("Running ANALYZE...")
        cursor.execute('ANALYZE')
        
        # Show index info
        print("\nCurrent indexes on market_snapshots:")
        indexes = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='market_snapshots'"
        ).fetchall()
        for idx in indexes:
            print(f"  - {idx[0]}")
        
        print("\n✓ Indexes created successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Failed to create indexes: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    add_indexes()
