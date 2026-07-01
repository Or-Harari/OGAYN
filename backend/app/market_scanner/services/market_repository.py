from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ...db.models import MarketSnapshot


class MarketRepository:
    def save_snapshots(self, db: Session, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            db_rows = [MarketSnapshot(**row) for row in rows]
            db.bulk_save_objects(db_rows)
            db.commit()
        except Exception as e:
            db.rollback()
            raise

    def latest_markets(
        self,
        db: Session,
        min_score: int | None = None,
        limit: int = 200,
        scanner_id: int | None = None,
        user_id: int | None = None,
    ) -> list[MarketSnapshot]:
        subquery = (
            db.query(
                MarketSnapshot.symbol.label("symbol"),
                MarketSnapshot.exchange.label("exchange"),
                func.max(MarketSnapshot.timestamp).label("max_timestamp"),
            )
            .group_by(MarketSnapshot.symbol, MarketSnapshot.exchange)
        )
        
        # Filter by scanner_id or user_id if provided
        if scanner_id is not None:
            subquery = subquery.filter(MarketSnapshot.scanner_id == scanner_id)
        if user_id is not None and scanner_id is None:
            subquery = subquery.filter(MarketSnapshot.user_id == user_id)
        
        subquery = subquery.subquery()

        query = (
            db.query(MarketSnapshot)
            .join(
                subquery,
                (MarketSnapshot.symbol == subquery.c.symbol)
                & (MarketSnapshot.exchange == subquery.c.exchange)
                & (MarketSnapshot.timestamp == subquery.c.max_timestamp),
            )
            .order_by(desc(MarketSnapshot.market_quality), desc(MarketSnapshot.timestamp))
        )

        if min_score is not None:
            query = query.filter(MarketSnapshot.market_quality >= min_score)

        return query.limit(max(1, min(1000, limit))).all()

    def top_markets(self, db: Session, limit: int = 50, min_score: int | None = None) -> list[MarketSnapshot]:
        return self.latest_markets(db=db, min_score=min_score, limit=limit)

    def latest_for_symbol(self, db: Session, symbol: str) -> MarketSnapshot | None:
        return (
            db.query(MarketSnapshot)
            .filter(MarketSnapshot.symbol == symbol.upper())
            .order_by(desc(MarketSnapshot.timestamp))
            .first()
        )

    def history_for_symbol(self, db: Session, symbol: str, limit: int = 200) -> list[MarketSnapshot]:
        return (
            db.query(MarketSnapshot)
            .filter(MarketSnapshot.symbol == symbol.upper())
            .order_by(desc(MarketSnapshot.timestamp))
            .limit(max(1, min(5000, limit)))
            .all()
        )

    @staticmethod
    def to_response_row(row: MarketSnapshot) -> dict[str, Any]:
        return {
            "id": row.id,
            "timestamp": row.timestamp,
            "exchange": row.exchange,
            "symbol": row.symbol,
            "price": row.price,
            "volume": row.volume,
            "atr": row.atr,
            "spread": row.spread,
            "funding": row.funding,
            "scores": {
                "liquidity": row.liquidity_score,
                "spread": row.spread_score,
                "atr": row.atr_score,

                "funding": row.funding_score,
                "tickSize": row.tick_score,
            },
            "marketQuality": row.market_quality,
            "reasons": json.loads(row.reasons_json or "{}"),
            "rawData": json.loads(row.raw_data_json or "{}"),
        }
