"""
Direct table creation for market cache
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backend.db"

def create_tables():
    print(f"Creating cache tables in: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create market_data_cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_data_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_timestamp INTEGER NOT NULL,
                symbol VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL DEFAULT 'binance',
                price FLOAT,
                volume FLOAT,
                atr FLOAT,
                spread FLOAT,
                open_interest FLOAT,
                funding_rate FLOAT,
                bid_price FLOAT,
                ask_price FLOAT,
                bid_qty FLOAT,
                ask_qty FLOAT,
                tick_size FLOAT,
                step_size FLOAT,
                raw_data_json TEXT
            )
        """)
        print("✓ Created market_data_cache table")
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_timestamp 
            ON market_data_cache(fetch_timestamp DESC)
        """)
        print("✓ Created idx_cache_timestamp index")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_symbol_timestamp 
            ON market_data_cache(symbol, fetch_timestamp DESC)
        """)
        print("✓ Created idx_cache_symbol_timestamp index")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_exchange 
            ON market_data_cache(exchange, fetch_timestamp DESC)
        """)
        print("✓ Created idx_cache_exchange index")
        
        # Create fetcher status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_data_fetcher_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_fetch_at INTEGER,
                fetch_interval INTEGER DEFAULT 5,
                is_running BOOLEAN DEFAULT 0,
                last_error TEXT
            )
        """)
        print("✓ Created market_data_fetcher_status table")
        
        # Insert default status
        cursor.execute("""
            INSERT OR IGNORE INTO market_data_fetcher_status (id, fetch_interval) 
            VALUES (1, 5)
        """)
        print("✓ Inserted default fetcher status")
        
        conn.commit()
        print("\n✅ All cache tables created successfully!")
        
        # Verify tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('market_data_cache', 'market_data_fetcher_status')
        """)
        tables = cursor.fetchall()
        print(f"\nVerified tables: {[t[0] for t in tables]}")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    create_tables()
