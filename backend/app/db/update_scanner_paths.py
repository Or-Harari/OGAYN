"""
Update scanner paths to use workspaces directory
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"

def migrate_paths():
    print(f"Updating scanner paths in: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Get all users
        users = conn.execute('SELECT id, workspace_root FROM users').fetchall()
        
        for user_id, workspace_root in users:
            print(f"\nProcessing user {user_id}: {workspace_root}")
            
            # Get all scanners for this user
            scanners = conn.execute(
                'SELECT id, name, output_base_path FROM scanner_configs WHERE user_id=?',
                (user_id,)
            ).fetchall()
            
            for scanner_id, name, old_path in scanners:
                # Compute new path: workspace_root/scanners/{name}
                new_path = str(Path(workspace_root) / 'scanners' / name)
                
                # Update database
                conn.execute(
                    'UPDATE scanner_configs SET output_base_path=? WHERE id=?',
                    (new_path, scanner_id)
                )
                
                print(f"  Scanner '{name}' (ID={scanner_id})")
                print(f"    Old: {old_path}")
                print(f"    New: {new_path}")
                
                # Create directory structure
                Path(new_path).mkdir(parents=True, exist_ok=True)
                (Path(new_path) / 'pairlists').mkdir(exist_ok=True)
                (Path(new_path) / 'snapshots').mkdir(exist_ok=True)
                (Path(new_path) / 'logs').mkdir(exist_ok=True)
                print(f"    Created directories")
        
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_paths()
