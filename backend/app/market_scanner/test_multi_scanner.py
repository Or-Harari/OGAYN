"""
Test script for multi-scanner functionality

This script verifies the multi-scanner architecture by:
1. Creating multiple scanner configs with different parameters
2. Running scans for each scanner
3. Verifying output paths and file generation
4. Checking database records
"""
import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.database import SessionLocal
from app.market_scanner.schemas import ScannerConfigCreate, ScannerConfigInternal
from app.market_scanner.services import (
    ScannerConfigRepository,
    MarketScannerService,
    PairlistService,
    MarketRepository
)


async def test_multi_scanner():
    """Test multi-scanner functionality."""
    print("=" * 80)
    print("MULTI-SCANNER TEST")
    print("=" * 80)
    
    db = SessionLocal()
    repo = ScannerConfigRepository()
    market_repo = MarketRepository()
    
    try:
        # 1. Create test scanners
        print("\n1. Creating test scanner configurations...")
        
        # Scanner A: Aggressive (low threshold, many pairs)
        scanner_a_config = ScannerConfigCreate(
            name="test-aggressive",
            exchange="binance",
            market_type="futures",
            enabled=True,
            interval_minutes=5,
            quote_asset="USDT",
            max_pairs=50,
            min_market_score=50,
            exclude_symbols=[]
        )
        
        # Scanner B: Conservative (high threshold, few pairs)
        scanner_b_config = ScannerConfigCreate(
            name="test-conservative",
            exchange="binance",
            market_type="futures",
            enabled=True,
            interval_minutes=5,
            quote_asset="USDT",
            max_pairs=10,
            min_market_score=80,
            exclude_symbols=[]
        )
        
        # Create or get existing scanners
        scanner_a = repo.get_by_user_and_name(db, 1, "test-aggressive")
        if not scanner_a:
            scanner_a = repo.create(db, 1, scanner_a_config)
            print(f"  ✓ Created Scanner A: {scanner_a.name} (ID={scanner_a.id})")
        else:
            print(f"  ⊘ Scanner A already exists: {scanner_a.name} (ID={scanner_a.id})")
        
        scanner_b = repo.get_by_user_and_name(db, 1, "test-conservative")
        if not scanner_b:
            scanner_b = repo.create(db, 1, scanner_b_config)
            print(f"  ✓ Created Scanner B: {scanner_b.name} (ID={scanner_b.id})")
        else:
            print(f"  ⊘ Scanner B already exists: {scanner_b.name} (ID={scanner_b.id})")
        
        # 2. Run scans
        print("\n2. Running scanner cycles...")
        
        config_a = ScannerConfigInternal.from_db_model(scanner_a)
        scanner_service_a = MarketScannerService(scanner_config=config_a)
        result_a = await scanner_service_a.run_cycle()
        
        if result_a.get("ok"):
            print(f"  ✓ Scanner A completed: {result_a.get('symbolsProcessed', 0)} symbols")
        else:
            print(f"  ✗ Scanner A failed: {result_a.get('error')}")
        
        config_b = ScannerConfigInternal.from_db_model(scanner_b)
        scanner_service_b = MarketScannerService(scanner_config=config_b)
        result_b = await scanner_service_b.run_cycle()
        
        if result_b.get("ok"):
            print(f"  ✓ Scanner B completed: {result_b.get('symbolsProcessed', 0)} symbols")
        else:
            print(f"  ✗ Scanner B failed: {result_b.get('error')}")
        
        # 3. Generate pairlists
        print("\n3. Generating pairlists...")
        
        pairlist_service_a = PairlistService(
            scanner_config=config_a,
            pair_format="slash"
        )
        summary_a = pairlist_service_a.generate_pairlists(db)
        print(f"  ✓ Scanner A pairlists: {len(summary_a.get('files', {}))} files")
        
        pairlist_service_b = PairlistService(
            scanner_config=config_b,
            pair_format="slash"
        )
        summary_b = pairlist_service_b.generate_pairlists(db)
        print(f"  ✓ Scanner B pairlists: {len(summary_b.get('files', {}))} files")
        
        # 4. Verify outputs
        print("\n4. Verifying outputs...")
        
        path_a = Path(config_a.output_base_path) / "pairlists" / "top_pairs.json"
        path_b = Path(config_b.output_base_path) / "pairlists" / "top_pairs.json"
        
        if path_a.exists():
            with open(path_a, "r") as f:
                data_a = json.load(f)
                print(f"  ✓ Scanner A top_pairs.json: {len(data_a.get('pairs', []))} pairs")
                print(f"    Path: {path_a}")
        else:
            print(f"  ✗ Scanner A top_pairs.json not found at {path_a}")
        
        if path_b.exists():
            with open(path_b, "r") as f:
                data_b = json.load(f)
                print(f"  ✓ Scanner B top_pairs.json: {len(data_b.get('pairs', []))} pairs")
                print(f"    Path: {path_b}")
        else:
            print(f"  ✗ Scanner B top_pairs.json not found at {path_b}")
        
        # 5. Verify database records
        print("\n5. Verifying database records...")
        
        markets_a = market_repo.latest_markets(
            db=db,
            scanner_id=scanner_a.id,
            min_score=config_a.min_market_score,
            limit=config_a.max_pairs
        )
        print(f"  ✓ Scanner A database records: {len(markets_a)} markets (score >= {config_a.min_market_score})")
        
        markets_b = market_repo.latest_markets(
            db=db,
            scanner_id=scanner_b.id,
            min_score=config_b.min_market_score,
            limit=config_b.max_pairs
        )
        print(f"  ✓ Scanner B database records: {len(markets_b)} markets (score >= {config_b.min_market_score})")
        
        # 6. Compare outputs
        print("\n6. Comparing scanner outputs...")
        
        print(f"  Scanner A (aggressive):")
        print(f"    - Max pairs: {config_a.max_pairs}")
        print(f"    - Min score: {config_a.min_market_score}")
        print(f"    - Actual pairs: {len(data_a.get('pairs', []))}")
        
        print(f"  Scanner B (conservative):")
        print(f"    - Max pairs: {config_b.max_pairs}")
        print(f"    - Min score: {config_b.min_market_score}")
        print(f"    - Actual pairs: {len(data_b.get('pairs', []))}")
        
        if len(data_a.get('pairs', [])) >= len(data_b.get('pairs', [])):
            print(f"  ✓ Verification: Scanner A has more/equal pairs (as expected)")
        else:
            print(f"  ⚠ Warning: Scanner B has more pairs than A (unexpected)")
        
        print("\n" + "=" * 80)
        print("TEST COMPLETED")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


async def test_config_crud():
    """Test scanner config CRUD operations."""
    print("\n" + "=" * 80)
    print("SCANNER CONFIG CRUD TEST")
    print("=" * 80)
    
    db = SessionLocal()
    repo = ScannerConfigRepository()
    
    try:
        # Create
        print("\n1. CREATE")
        config = ScannerConfigCreate(
            name="test-crud",
            exchange="binance",
            market_type="futures",
            quote_asset="USDT",
            max_pairs=20
        )
        db_config = repo.create(db, 1, config)
        print(f"  ✓ Created scanner: {db_config.name} (ID={db_config.id})")
        
        # Read
        print("\n2. READ")
        retrieved = repo.get(db, db_config.id)
        print(f"  ✓ Retrieved scanner: {retrieved.name}")
        
        # Update
        print("\n3. UPDATE")
        from app.market_scanner.schemas import ScannerConfigUpdate
        update = ScannerConfigUpdate(max_pairs=30, min_market_score=75)
        updated = repo.update(db, db_config.id, update)
        
        config_json = json.loads(updated.config_json)
        print(f"  ✓ Updated scanner: max_pairs={config_json['maxPairs']}, min_score={config_json['minMarketScore']}")
        
        # List
        print("\n4. LIST")
        all_configs = repo.list_by_user(db, 1)
        print(f"  ✓ User has {len(all_configs)} scanner(s)")
        
        # Delete
        print("\n5. DELETE")
        success = repo.delete(db, db_config.id)
        if success:
            print(f"  ✓ Deleted scanner (ID={db_config.id})")
        
        print("\n" + "=" * 80)
        print("CRUD TEST COMPLETED")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ CRUD test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting multi-scanner tests...\n")
    
    # Run tests
    asyncio.run(test_config_crud())
    asyncio.run(test_multi_scanner())
    
    print("\n✓ All tests completed!")
