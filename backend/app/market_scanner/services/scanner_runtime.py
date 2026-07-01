from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from ...db.database import SessionLocal
from .market_scanner_service import MarketScannerService
from .scanner_config_repository import ScannerConfigRepository
from ..schemas import ScannerConfigInternal

logger = logging.getLogger(__name__)


class ScannerRuntime:
    def __init__(self):
        # Legacy single scanner service (backward compatibility)
        self.service = MarketScannerService()
        
        self.config_repo = ScannerConfigRepository()
        self.task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()
        self._use_multi_scanner = os.getenv("MULTI_SCANNER_ENABLED", "true").lower() == "true"

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.stop_event.clear()
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self.stop_event.set()
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def run_once(self) -> dict:
        """Legacy single scanner run (backward compatibility)."""
        result = await self.service.run_cycle()
        # Note: Pairlist generation is now handled within scanner service
        return result

    async def run_multi_scanner(self) -> dict[str, Any]:
        """Run all enabled scanner configs."""
        results = {"scanners": [], "errors": []}
        
        def _load_configs():
            db = SessionLocal()
            try:
                # Ensure default scanner exists for backward compatibility
                self.config_repo.ensure_default_scanner(db, user_id=1)
                return self.config_repo.list_enabled(db)
            finally:
                db.close()
        
        try:
            db_configs = await asyncio.to_thread(_load_configs)
            scanner_configs = [ScannerConfigInternal.from_db_model(cfg) for cfg in db_configs]
            
            logger.info(f"Running {len(scanner_configs)} enabled scanner(s)")
            
            # Run each scanner
            for config in scanner_configs:
                try:
                    # Create scanner service with config
                    scanner_service = MarketScannerService(scanner_config=config)
                    
                    # Run scan (now includes output writing to DB and JSON)
                    scan_result = await scanner_service.run_cycle()
                    
                    if scan_result.get("ok"):
                        results["scanners"].append({
                            "scanner_id": config.id,
                            "scanner_name": config.name,
                            "user_id": config.user_id,
                            "symbols_processed": scan_result.get("symbolsProcessed", 0),
                            "output_symbols": scan_result.get("outputSymbols", 0),
                            "output_path": config.output_base_path
                        })
                        
                        logger.info(
                            f"Scanner '{config.name}' (ID={config.id}): "
                            f"processed {scan_result.get('symbolsProcessed', 0)} symbols, "
                            f"output {scan_result.get('outputSymbols', 0)} top symbols"
                        )
                    else:
                        error = scan_result.get("error", "Unknown error")
                        results["errors"].append(f"Scanner '{config.name}' failed: {error}")
                        logger.error(f"Scanner '{config.name}' (ID={config.id}) failed: {error}")
                        
                except Exception as e:
                    error_msg = f"Scanner '{config.name}' (ID={config.id}) error: {str(e)}"
                    results["errors"].append(error_msg)
                    logger.exception(error_msg)
            
            return results
            
        except Exception as e:
            logger.exception("Multi-scanner run failed")
            return {"scanners": [], "errors": [str(e)]}

    async def _loop(self):
        interval_seconds = int(os.getenv("MARKET_SCANNER_INTERVAL_SECONDS", "300"))
        immediate_run = os.getenv("MARKET_SCANNER_RUN_AT_STARTUP", "true").lower() == "true"

        if immediate_run:
            try:
                if self._use_multi_scanner:
                    await self.run_multi_scanner()
                else:
                    await self.run_once()
            except Exception:
                logger.exception("Initial scanner run failed")

        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=max(30, interval_seconds))
            except asyncio.TimeoutError:
                try:
                    if self._use_multi_scanner:
                        await self.run_multi_scanner()
                    else:
                        await self.run_once()
                except Exception:
                    logger.exception("Scheduled scanner run failed")


scanner_runtime = ScannerRuntime()
