"""
Scanner Scheduler Service
Automatically runs scanners on their configured intervals
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ...db.database import SessionLocal
from .market_scanner_service import MarketScannerService
from .scanner_config_repository import ScannerConfigRepository

logger = logging.getLogger(__name__)


class ScannerSchedulerService:
    """
    Background service that runs enabled scanners on their configured intervals.
    Each scanner runs independently based on its interval setting.
    """
    
    def __init__(self):
        self._running = False
        self._scanner_tasks: dict[int, asyncio.Task] = {}  # scanner_id -> task
        self._check_interval = 30  # Check for new/updated scanners every 30 seconds
        self._main_task = None
    
    async def _run_scanner_once(self, scanner_id: int, scanner_config) -> dict[str, Any]:
        """Run a single scanner scan"""
        try:
            logger.info(f"Running scanner '{scanner_config.name}' (ID={scanner_id})")
            
            # Create scanner service
            scanner_service = MarketScannerService(scanner_config=scanner_config)
            
            # Run scan (now includes output writing to DB and JSON)
            scan_result = await scanner_service.run_cycle()
            
            if scan_result.get("ok"):
                # Update last_run_at
                def _update_last_run():
                    from sqlalchemy import text
                    db = SessionLocal()
                    try:
                        db.execute(
                            text("UPDATE scanner_configs SET last_run_at=:ts WHERE id=:id"),
                            {"ts": int(time.time()), "id": scanner_id}
                        )
                        db.commit()
                    finally:
                        db.close()
                
                await asyncio.to_thread(_update_last_run)
                
                logger.info(
                    f"Scanner '{scanner_config.name}' completed: "
                    f"{scan_result.get('symbolsProcessed', 0)} symbols scored, "
                    f"{scan_result.get('outputSymbols', 0)} outputs written"
                )
            else:
                logger.error(f"Scanner '{scanner_config.name}' failed: {scan_result.get('error')}")
            
            return scan_result
            
        except Exception as e:
            logger.exception(f"Error running scanner {scanner_id}: {e}")
            return {"ok": False, "error": str(e), "timestamp": int(time.time())}
    
    async def _scanner_loop(self, scanner_id: int):
        """Loop for a single scanner"""
        logger.info(f"Starting loop for scanner ID={scanner_id}")
        
        while self._running and scanner_id in self._scanner_tasks:
            try:
                # Get current scanner config
                def _get_config():
                    db = SessionLocal()
                    try:
                        repo = ScannerConfigRepository()
                        return repo.get_internal_config(db, scanner_id)
                    finally:
                        db.close()
                
                scanner_config = await asyncio.to_thread(_get_config)
                
                if not scanner_config or not scanner_config.enabled:
                    logger.info(f"Scanner {scanner_id} disabled or not found, stopping loop")
                    break
                
                # Check if it's time to run
                now = int(time.time())
                last_run = scanner_config.last_run_at or 0
                interval_seconds = scanner_config.interval_minutes * 60
                
                if now - last_run >= interval_seconds:
                    # Time to run!
                    await self._run_scanner_once(scanner_id, scanner_config)
                
                # Sleep for a bit before checking again (check every 10 seconds)
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logger.info(f"Scanner loop {scanner_id} cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in scanner loop {scanner_id}: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _main_loop(self):
        """Main scheduler loop that manages all scanner tasks"""
        logger.info("Scanner scheduler main loop started")
        
        while self._running:
            try:
                # Get all enabled scanners
                def _get_scanners():
                    db = SessionLocal()
                    try:
                        repo = ScannerConfigRepository()
                        return repo.list_enabled(db)
                    finally:
                        db.close()
                
                enabled_scanners = await asyncio.to_thread(_get_scanners)
                
                # Get current scanner IDs
                enabled_ids = {s.id for s in enabled_scanners}
                current_ids = set(self._scanner_tasks.keys())
                
                # Start new scanners
                for scanner_id in enabled_ids - current_ids:
                    logger.info(f"Starting scheduler for scanner {scanner_id}")
                    task = asyncio.create_task(self._scanner_loop(scanner_id))
                    self._scanner_tasks[scanner_id] = task
                
                # Stop removed/disabled scanners
                for scanner_id in current_ids - enabled_ids:
                    logger.info(f"Stopping scheduler for scanner {scanner_id}")
                    task = self._scanner_tasks.pop(scanner_id)
                    task.cancel()
                
                # Sleep before next check
                await asyncio.sleep(self._check_interval)
                
            except asyncio.CancelledError:
                logger.info("Main scheduler loop cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in main scheduler loop: {e}")
                await asyncio.sleep(60)
        
        # Cancel all scanner tasks
        for task in self._scanner_tasks.values():
            task.cancel()
        
        self._scanner_tasks.clear()
        logger.info("Scanner scheduler main loop stopped")
    
    def start(self):
        """Start the scheduler service"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._main_task = asyncio.create_task(self._main_loop())
        logger.info("Scanner scheduler service started")
    
    def stop(self):
        """Stop the scheduler service"""
        if not self._running:
            return
        
        self._running = False
        if self._main_task:
            self._main_task.cancel()
        logger.info("Scanner scheduler service stopped")
    
    def status(self) -> dict[str, Any]:
        """Get scheduler status"""
        return {
            "running": self._running,
            "active_scanners": len(self._scanner_tasks),
            "scanner_ids": list(self._scanner_tasks.keys())
        }
    
    async def run_scanner_now(self, scanner_id: int) -> dict[str, Any]:
        """Manually trigger a scanner run (for "Run Now" button)"""
        def _get_config():
            db = SessionLocal()
            try:
                repo = ScannerConfigRepository()
                return repo.get_internal_config(db, scanner_id)
            finally:
                db.close()
        
        scanner_config = await asyncio.to_thread(_get_config)
        
        if not scanner_config:
            return {"ok": False, "error": "Scanner not found", "timestamp": int(time.time())}
        
        return await self._run_scanner_once(scanner_id, scanner_config)
