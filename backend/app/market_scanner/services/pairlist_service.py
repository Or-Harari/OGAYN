from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from sqlalchemy.orm import Session

from ...db.database import SessionLocal
from .scanner_output_repository import ScannerOutputRepository

if TYPE_CHECKING:
    from ..schemas import ScannerConfigInternal

logger = logging.getLogger(__name__)


class PairlistService:
    """
    Service for generating pairlist JSON files from scanner outputs.
    Each scanner writes a single JSON file: remote_pairlist.json
    This file is used by Freqtrade's RemotePairList plugin.
    """
    
    def __init__(
        self,
        scanner_config: 'ScannerConfigInternal',
        refresh_period: int = 300,
        pair_format: str = "slash",  # "slash" (XRP/USDT) or "plain" (XRPUSDT)
    ):
        self.scanner_config = scanner_config
        self.output_dir = Path(scanner_config.output_base_path) / "pairlists"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.scanner_id = scanner_config.id
        self.user_id = scanner_config.user_id
        self.refresh_period = refresh_period
        self.pair_format = pair_format.lower()
        
        self.output_repository = ScannerOutputRepository()

    def _format_symbol(self, symbol: str) -> str:
        """Convert BTCUSDT to BTC/USDT or keep as-is based on pair_format."""
        if self.pair_format == "slash":
            # Binance futures format: BTCUSDT -> BTC/USDT
            # Assumes USDT quote (since scanner only fetches USDT pairs)
            if symbol.endswith("USDT"):
                base = symbol[:-4]
                return f"{base}/USDT"
            return symbol
        return symbol

    def generate_pairlist_from_outputs(
        self,
        outputs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Generate single pairlist JSON file from scanner outputs.
        This is the main method called after scanner completes.
        
        Returns:
            Summary with file path and count
        """
        try:
            # Extract symbols in rank order
            pairs = [self._format_symbol(output["symbol"]) for output in outputs]
            
            # Create Freqtrade RemotePairList format
            pairlist_data = {
                "pairs": pairs,
                "refresh_period": self.refresh_period
            }
            
            # Write single JSON file
            filepath = self.output_dir / "remote_pairlist.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(pairlist_data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                f"Generated pairlist for scanner '{self.scanner_config.name}' "
                f"with {len(pairs)} pairs at {filepath}"
            )
            
            return {
                "success": True,
                "file": str(filepath),
                "count": len(pairs),
                "scanner_id": self.scanner_id,
                "scanner_name": self.scanner_config.name,
            }
            
        except Exception as e:
            error_msg = f"Failed to generate pairlist: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "scanner_id": self.scanner_id,
                "scanner_name": self.scanner_config.name,
            }

    def generate_pairlist_from_db(self, db: Session | None = None) -> dict[str, Any]:
        """
        Generate pairlist JSON file by reading from scanner_outputs table.
        Useful for regenerating files without running the full scanner.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Fetch current outputs from DB
            db_outputs = self.output_repository.get_scanner_outputs(
                db=db,
                scanner_id=self.scanner_id
            )
            
            if not db_outputs:
                logger.warning(
                    f"No scanner outputs found for scanner_id={self.scanner_id}"
                )
                return {
                    "success": False,
                    "error": "No scanner outputs available",
                    "scanner_id": self.scanner_id,
                }
            
            # Convert to output dict format
            outputs = [
                {"symbol": out.symbol, "rank": out.rank}
                for out in db_outputs
            ]
            
            return self.generate_pairlist_from_outputs(outputs)
            
        finally:
            if should_close:
                db.close()

    def read_pairlist(self) -> dict[str, Any] | None:
        """Read the current pairlist file if it exists."""
        filepath = self.output_dir / "remote_pairlist.json"
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {filepath}: {e}")
            return None

    def get_pairlist_info(self) -> dict[str, Any] | None:
        """Get metadata about the current pairlist file."""
        filepath = self.output_dir / "remote_pairlist.json"
        if not filepath.exists():
            return None
        
        try:
            data = self.read_pairlist()
            if data:
                return {
                    "filename": filepath.name,
                    "count": len(data.get("pairs", [])),
                    "refresh_period": data.get("refresh_period"),
                    "path": str(filepath),
                    "scanner_id": self.scanner_id,
                    "scanner_name": self.scanner_config.name,
                }
        except Exception as e:
            logger.error(f"Failed to get pairlist info: {e}")
        
        return None
