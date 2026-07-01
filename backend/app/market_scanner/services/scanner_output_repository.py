"""
Repository for scanner output operations.
Handles saving and retrieving current scanner outputs.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...db.models import ScannerOutput


class ScannerOutputRepository:
    """
    Repository for managing scanner outputs.
    Each scanner run clears old outputs and writes fresh data.
    """
    
    def clear_scanner_outputs(self, db: Session, scanner_id: int) -> None:
        """
        Clear all existing outputs for a specific scanner.
        Called before writing new outputs to ensure fresh data.
        """
        try:
            db.query(ScannerOutput).filter(
                ScannerOutput.scanner_id == scanner_id
            ).delete()
            db.commit()
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to clear scanner outputs: {e}")
    
    def save_outputs(self, db: Session, outputs: list[dict[str, Any]]) -> None:
        """
        Save scanner outputs in bulk.
        Expects outputs to already be sorted by rank.
        """
        if not outputs:
            return
        
        try:
            db_rows = [ScannerOutput(**output) for output in outputs]
            db.bulk_save_objects(db_rows)
            db.commit()
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to save scanner outputs: {e}")
    
    def replace_scanner_outputs(
        self,
        db: Session,
        scanner_id: int,
        outputs: list[dict[str, Any]]
    ) -> None:
        """
        Atomically replace all outputs for a scanner (clear + save).
        This is the main method to use for updating scanner outputs.
        """
        try:
            # Clear old outputs
            self.clear_scanner_outputs(db, scanner_id)
            
            # Save new outputs
            self.save_outputs(db, outputs)
            
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to replace scanner outputs: {e}")
    
    def get_scanner_outputs(
        self,
        db: Session,
        scanner_id: int,
        limit: int | None = None
    ) -> list[ScannerOutput]:
        """
        Get current outputs for a specific scanner, ordered by rank.
        """
        query = (
            db.query(ScannerOutput)
            .filter(ScannerOutput.scanner_id == scanner_id)
            .order_by(ScannerOutput.rank)
        )
        
        if limit is not None:
            query = query.limit(max(1, min(1000, limit)))
        
        return query.all()
    
    def get_user_scanner_outputs(
        self,
        db: Session,
        user_id: int,
        scanner_id: int | None = None,
        limit: int | None = None
    ) -> list[ScannerOutput]:
        """
        Get outputs for a user, optionally filtered by scanner.
        """
        query = (
            db.query(ScannerOutput)
            .filter(ScannerOutput.user_id == user_id)
        )
        
        if scanner_id is not None:
            query = query.filter(ScannerOutput.scanner_id == scanner_id)
        
        query = query.order_by(
            ScannerOutput.scanner_id,
            ScannerOutput.rank
        )
        
        if limit is not None:
            query = query.limit(max(1, min(1000, limit)))
        
        return query.all()
    
    def get_latest_generation_timestamp(
        self,
        db: Session,
        scanner_id: int
    ) -> int | None:
        """
        Get the timestamp of the latest output generation for a scanner.
        Returns None if no outputs exist.
        """
        result = (
            db.query(ScannerOutput.generated_at)
            .filter(ScannerOutput.scanner_id == scanner_id)
            .order_by(desc(ScannerOutput.generated_at))
            .first()
        )
        
        return result[0] if result else None
    
    @staticmethod
    def to_response_dict(output: ScannerOutput) -> dict[str, Any]:
        """Convert ScannerOutput model to response dictionary."""
        reasons = {}
        if output.reasons_json:
            try:
                reasons = json.loads(output.reasons_json)
            except json.JSONDecodeError:
                reasons = {}
        
        return {
            "id": output.id,
            "scanner_id": output.scanner_id,
            "user_id": output.user_id,
            "generated_at": output.generated_at,
            "symbol": output.symbol,
            "exchange": output.exchange,
            "rank": output.rank,
            "price": output.price,
            "volume": output.volume,
            "atr": output.atr,
            "spread": output.spread,
            "funding": output.funding,
            "total_score": output.total_score,
            "scores": {
                "liquidity": output.liquidity_score,
                "volatility": output.volatility_score,
                "spread": output.spread_score,
                "funding": output.funding_score,
                "tick": output.tick_score,
            },
            "reasons": reasons,
        }
