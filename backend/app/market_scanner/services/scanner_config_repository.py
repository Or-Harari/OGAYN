"""
Repository for scanner config database operations
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ...db.models import ScannerConfig
from ..schemas import ScannerConfigCreate, ScannerConfigInternal, ScannerConfigUpdate

logger = logging.getLogger(__name__)


class ScannerConfigRepository:
    """Repository for managing scanner configurations."""

    @staticmethod
    def _compute_output_path(db: Session, user_id: int, scanner_name: str) -> str:
        """Compute output path for scanner data using user's workspace_root."""
        from ...db.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # User workspace_root points to workspaces/user{id}/user
        # We'll create scanners directory under user's workspace root
        workspace_root = Path(user.workspace_root)
        scanner_path = workspace_root / "scanners" / scanner_name
        return str(scanner_path)

    @staticmethod
    def _config_to_json(config_create: ScannerConfigCreate | ScannerConfigUpdate | dict[str, Any]) -> str:
        """Convert config schema to JSON string for database storage."""
        if isinstance(config_create, dict):
            data = config_create
        else:
            data = config_create.model_dump(exclude={'name', 'exchange', 'market_type', 'enabled', 'interval_minutes'})
        
        # DEBUG: Log what we're receiving
        print(f"[DEBUG _config_to_json] recent_activity in data: {'recent_activity' in data}")
        print(f"[DEBUG _config_to_json] recent_activity value: {data.get('recent_activity')}")
        print(f"[DEBUG _config_to_json] recent_activity type: {type(data.get('recent_activity'))}")
        
        # Convert to camelCase for JSON storage
        config_json = {
            'quoteAsset': data.get('quote_asset', 'USDT'),
            'maxPairs': data.get('max_pairs', 30),
            'minMarketScore': data.get('min_market_score', 70),
            'includeSymbols': data.get('include_symbols', []),
            'excludeSymbols': data.get('exclude_symbols', []),
            'scoringWeights': {
                k: v for k, v in (data.get('scoring_weights', {}) if isinstance(data.get('scoring_weights'), dict) else data.get('scoring_weights', {}).model_dump()).items()
            } if 'scoring_weights' in data and data['scoring_weights'] else {
                'liquidity': 30, 'volatility': 25, 'spread': 25,
                'funding': 10, 'tradeCount': 10, 'recentActivity': 0
            },
            'scoringThresholds': {
                k: v for k, v in (data.get('scoring_thresholds', {}) if isinstance(data.get('scoring_thresholds'), dict) else data.get('scoring_thresholds', {}).model_dump()).items()
            } if 'scoring_thresholds' in data and data['scoring_thresholds'] else {
                'minQuoteVolume24h': 30000000, 'excellentQuoteVolume24h': 500000000,
                'minAtrPct': 0.5, 'idealAtrPctLow': 1.0, 'idealAtrPctHigh': 3.0,
                        'maxAtrPct': 6.0, 'maxSpreadPct': 0.1,
                        'maxSpreadToAtrRatio': 0.10,
                        'normalFundingAbs': 0.0001,
                        'maxFundingAbs': 0.001
            },
            'recentActivity': {
                k: v for k, v in (data.get('recent_activity', {}) if isinstance(data.get('recent_activity'), dict) else data.get('recent_activity', {}).model_dump()).items()
            } if 'recent_activity' in data and data['recent_activity'] else {
                'enabled': True,
                'primaryWindow': '1h',
                'secondaryWindow': '4h',
                'use1d': True,
                'staleAfterSeconds': 180,
            },
            'recentActivityThresholds': {
                k: v for k, v in (data.get('recent_activity_thresholds', {}) if isinstance(data.get('recent_activity_thresholds'), dict) else data.get('recent_activity_thresholds', {}).model_dump()).items()
            } if 'recent_activity_thresholds' in data and data['recent_activity_thresholds'] else {
                'minQuoteVolume1h': 1_000_000,
                'excellentQuoteVolume1h': 25_000_000,
                'minQuoteVolume4h': 5_000_000,
                'excellentQuoteVolume4h': 100_000_000,
                'minQuoteVolume1d': 20_000_000,
                'excellentQuoteVolume1d': 500_000_000,
                'minTrades1h': 500,
                'excellentTrades1h': 10_000,
                'minTrades4h': 1_500,
                'excellentTrades4h': 30_000,
            },
        }
        
        return json.dumps(config_json, ensure_ascii=False)

    def create(self, db: Session, user_id: int, config: ScannerConfigCreate) -> ScannerConfig:
        """Create a new scanner configuration."""
        output_path = self._compute_output_path(db, user_id, config.name)
        
        db_config = ScannerConfig(
            user_id=user_id,
            name=config.name,
            exchange=config.exchange,
            market_type=config.market_type,
            enabled=config.enabled,
            interval_minutes=config.interval_minutes,
            config_json=self._config_to_json(config),
            output_base_path=output_path
        )
        
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        
        # Create output directory
        Path(output_path).mkdir(parents=True, exist_ok=True)
        (Path(output_path) / "pairlists").mkdir(exist_ok=True)
        (Path(output_path) / "snapshots").mkdir(exist_ok=True)
        (Path(output_path) / "logs").mkdir(exist_ok=True)
        
        logger.info(f"Created scanner config: {config.name} (ID={db_config.id}) for user {user_id}")
        return db_config

    def get(self, db: Session, scanner_id: int) -> ScannerConfig | None:
        """Get scanner configuration by ID."""
        return db.query(ScannerConfig).filter(ScannerConfig.id == scanner_id).first()

    def get_by_user_and_name(self, db: Session, user_id: int, name: str) -> ScannerConfig | None:
        """Get scanner configuration by user ID and name."""
        return db.query(ScannerConfig).filter(
            ScannerConfig.user_id == user_id,
            ScannerConfig.name == name
        ).first()

    def list_by_user(self, db: Session, user_id: int, enabled_only: bool = False) -> list[ScannerConfig]:
        """List all scanner configurations for a user."""
        query = db.query(ScannerConfig).filter(ScannerConfig.user_id == user_id)
        if enabled_only:
            query = query.filter(ScannerConfig.enabled == True)
        return query.order_by(ScannerConfig.created_at.desc()).all()

    def list_enabled(self, db: Session) -> list[ScannerConfig]:
        """List all enabled scanner configurations across all users."""
        return db.query(ScannerConfig).filter(ScannerConfig.enabled == True).all()

    def update(self, db: Session, scanner_id: int, config_update: ScannerConfigUpdate) -> ScannerConfig | None:
        """Update scanner configuration."""
        db_config = self.get(db, scanner_id)
        if not db_config:
            return None
        
        update_data = config_update.model_dump(exclude_unset=True)
        
        # DEBUG: Log update data
        print(f"[DEBUG update] update_data keys: {update_data.keys()}")
        print(f"[DEBUG update] 'recent_activity' in update_data: {'recent_activity' in update_data}")
        if 'recent_activity' in update_data:
            print(f"[DEBUG update] recent_activity value: {update_data['recent_activity']}")
            print(f"[DEBUG update] recent_activity is not None: {update_data['recent_activity'] is not None}")
        
        # Update simple fields
        for field in ['name', 'exchange', 'market_type', 'enabled', 'interval_minutes']:
            if field in update_data:
                setattr(db_config, field, update_data[field])
        
        # Update JSON config
        if any(k in update_data for k in ['quote_asset', 'max_pairs', 'min_market_score', 
                                           'include_symbols', 'exclude_symbols',
                                           'scoring_weights', 'scoring_thresholds',
                                           'recent_activity', 'recent_activity_thresholds']):
            existing_config = json.loads(db_config.config_json)
            
            # Merge updates
            if 'quote_asset' in update_data:
                existing_config['quoteAsset'] = update_data['quote_asset']
            if 'max_pairs' in update_data:
                existing_config['maxPairs'] = update_data['max_pairs']
            if 'min_market_score' in update_data:
                existing_config['minMarketScore'] = update_data['min_market_score']
            if 'include_symbols' in update_data:
                existing_config['includeSymbols'] = update_data['include_symbols']
            if 'exclude_symbols' in update_data:
                existing_config['excludeSymbols'] = update_data['exclude_symbols']
            if 'scoring_weights' in update_data and update_data['scoring_weights'] is not None:
                weights = update_data['scoring_weights']
                # If it's a dict, use it directly; if it's a model, call model_dump()
                existing_config['scoringWeights'] = weights if isinstance(weights, dict) else weights.model_dump()
            if 'scoring_thresholds' in update_data and update_data['scoring_thresholds'] is not None:
                thresholds = update_data['scoring_thresholds']
                # If it's a dict, use it directly; if it's a model, call model_dump()
                existing_config['scoringThresholds'] = thresholds if isinstance(thresholds, dict) else thresholds.model_dump()
            if 'recent_activity' in update_data and update_data['recent_activity'] is not None:
                recent_activity = update_data['recent_activity']
                print(f"[DEBUG update] Saving recent_activity: {recent_activity}")
                existing_config['recentActivity'] = (
                    recent_activity if isinstance(recent_activity, dict) else recent_activity.model_dump()
                )
                print(f"[DEBUG update] Saved as: {existing_config['recentActivity']}")
            else:
                print(f"[DEBUG update] NOT saving recent_activity (not in update_data or is None)")
            if 'recent_activity_thresholds' in update_data and update_data['recent_activity_thresholds'] is not None:
                recent_thresholds = update_data['recent_activity_thresholds']
                existing_config['recentActivityThresholds'] = (
                    recent_thresholds if isinstance(recent_thresholds, dict) else recent_thresholds.model_dump()
                )
            
            db_config.config_json = json.dumps(existing_config, ensure_ascii=False)
            
            # DEBUG: Log final config before saving
            print(f"[DEBUG update] Final config_json recentActivity: {existing_config.get('recentActivity')}")
        
        # Update output path if name changed
        if 'name' in update_data:
            db_config.output_base_path = self._compute_output_path(db, db_config.user_id, update_data['name'])
        
        db.commit()
        db.refresh(db_config)
        
        logger.info(f"Updated scanner config: {db_config.name} (ID={scanner_id})")
        return db_config

    def delete(self, db: Session, scanner_id: int) -> bool:
        """Delete scanner configuration."""
        db_config = self.get(db, scanner_id)
        if not db_config:
            return False
        
        logger.info(f"Deleting scanner config: {db_config.name} (ID={scanner_id})")
        db.delete(db_config)
        db.commit()
        return True

    def get_internal_config(self, db: Session, scanner_id: int) -> ScannerConfigInternal | None:
        """Get scanner configuration as internal config model."""
        db_config = self.get(db, scanner_id)
        if not db_config:
            return None
        return ScannerConfigInternal.from_db_model(db_config)

    def ensure_default_scanner(self, db: Session, user_id: int = 1) -> ScannerConfig:
        """Ensure default scanner exists for backward compatibility."""
        existing = self.get_by_user_and_name(db, user_id, "default")
        if existing:
            return existing
        
        logger.info(f"Creating default scanner for user {user_id}")
        
        default_config = ScannerConfigCreate(
            name="default",
            exchange="binance",
            market_type="futures",
            enabled=True,
            interval_minutes=5,
            quote_asset="USDT",
            max_pairs=100,
            min_market_score=50,
            include_symbols=[],
            exclude_symbols=[]
        )
        
        return self.create(db, user_id, default_config)
