"""
Cleanup old scanner snapshots to keep database size manageable
Keeps only the last 7 days of snapshots per scanner
"""
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"

def cleanup_old_snapshots(days_to_keep=7):
    print(f"Cleaning up snapshots older than {days_to_keep} days...")
    
    cutoff_timestamp = int(time.time()) - (days_to_keep * 24 * 60 * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Count snapshots to delete
        count_result = cursor.execute(
            'SELECT COUNT(*) FROM market_snapshots WHERE timestamp < ?',
            (cutoff_timestamp,)
        ).fetchone()
        count = count_result[0]
        
        if count == 0:
            print("No old snapshots to delete.")
            return
        
        print(f"Found {count} snapshots older than {days_to_keep} days")
        
        # Delete old snapshots
        cursor.execute(
            'DELETE FROM market_snapshots WHERE timestamp < ?',
            (cutoff_timestamp,)
        )
        
        conn.commit()
        
        # Vacuum to reclaim disk space
        print("Running VACUUM to reclaim disk space...")
        cursor.execute('VACUUM')
        
        print(f"\n✓ Deleted {count} old snapshots!")
        
        # Show current counts
        print("\nCurrent snapshot counts by scanner:")
        scanners = cursor.execute('''
            SELECT s.name, COUNT(m.id) as count
            FROM scanner_configs s
            LEFT JOIN market_snapshots m ON s.id = m.scanner_id
            GROUP BY s.id, s.name
        ''').fetchall()
        
        for name, count in scanners:
            print(f"  {name}: {count} snapshots")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Cleanup failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    cleanup_old_snapshots(days_to_keep=7)
