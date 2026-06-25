from typing import Any, Dict, Optional, List
from datetime import datetime
from pandas import DataFrame
from V3 import V3


class SupplyDemandStructureStrategyHTF_TrendV2(V3):
    strategy_name = "SupplyDemandStructureStrategyHTF_TrendV2"
    # Profit-only exit: disable ROI to rely solely on custom_exit at 100%
    minimal_roi = {"0": 1.0}  # 100% ROI threshold (matches custom_exit logic)
    stoploss = -10.0
    use_custom_stoploss = False
    use_exit_signal = False
    max_entry_position_adjustment = 10
    max_open_trades = 10
    can_short = True
    default_leverage: float = 10.0

    # Enable liquidation-based DCA
    position_adjustment_enable = True
    dca_enable: bool = True
    dca_mode: str = "martingale"  # or "uniform"
    dca_liq_buffer_pct: float = 10.0  # Trigger DCA when within this % above liquidation
    dca_max_adds: int = 10
    dca_total_budget: float = 2500.0
    dca_cooldown_minutes: int = 15  # Minimum minutes between DCA adds
    futures_leverage: Optional[float] = None  # Default set in __init__ if not provided
    dca_liq_trigger_ratio: Optional[float] = None
    liq_mmr_adjust_pct: float = 0.0
    # Leverage controls (explicit for TrendV2)
    default_leverage: float = 10.0
    long_leverage: Optional[float] = None
    short_leverage: Optional[float] = None
    max_config_leverage: Optional[float] = None
    # Slightly looser RR to allow trend participation
    rr_min = 1
    # Fair Value Gap usage parameters
    use_htf_fvg: bool = True
    htf_fvg_max_age: int = 48        # max age (1h candles) to consider FVG valid
    htf_fvg_touch_ratio: float = 0.35  # fraction into gap considered acceptable (0 = near discount for longs)

    def populate_entry_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        # Base entries (LTF only) before HTF filters
        df = super().populate_entry_trend(df, metadata)

        # Keep raw snapshot for pruning diagnostics
        df["enter_long_raw"] = df.get("enter_long", 0)
        df["enter_short_raw"] = df.get("enter_short", 0)

        # HTF columns now suffixed via merge_informative_pair (e.g. htf_trend_1h)
        htf_suffix = f"_{self.informative_timeframe}"  # usually _1h
        trend_col = f"htf_trend{htf_suffix}"
        bull_low_col = f"htf_bull_fvg_low{htf_suffix}"
        bull_high_col = f"htf_bull_fvg_high{htf_suffix}"
        bull_age_col = f"htf_bull_fvg_age{htf_suffix}"
        bear_low_col = f"htf_bear_fvg_low{htf_suffix}"
        bear_high_col = f"htf_bear_fvg_high{htf_suffix}"
        bear_age_col = f"htf_bear_fvg_age{htf_suffix}"

        if trend_col not in df.columns:
            return df  # HTF data not merged yet

        htf_trend = df[trend_col]

        # Apply strict trend filter
        long_mask = df["enter_long"] == 1
        short_mask = df["enter_short"] == 1
        df.loc[long_mask & (htf_trend != "UP"), "enter_long"] = 0
        df.loc[short_mask & (htf_trend != "DOWN"), "enter_short"] = 0

        # Post-trend snapshot
        df["enter_long_after_trend"] = df["enter_long"]
        df["enter_short_after_trend"] = df["enter_short"]

        if self.use_htf_fvg:
            required = {bull_low_col, bull_high_col, bull_age_col, bear_low_col, bear_high_col, bear_age_col}
            if required.issubset(df.columns):
                import pandas as pd
                bull_low = pd.to_numeric(df[bull_low_col], errors="coerce")
                bull_high = pd.to_numeric(df[bull_high_col], errors="coerce")
                bull_age = pd.to_numeric(df[bull_age_col], errors="coerce")
                bear_low = pd.to_numeric(df[bear_low_col], errors="coerce")
                bear_high = pd.to_numeric(df[bear_high_col], errors="coerce")
                bear_age = pd.to_numeric(df[bear_age_col], errors="coerce")

                bull_valid = bull_low.notna() & bull_high.notna() & (bull_age <= self.htf_fvg_max_age)
                gap_height_bull = (bull_high - bull_low)
                pos_in_bull_gap = (df["close"] - bull_low) / gap_height_bull.replace(0, pd.NA)
                long_fvg_ok = bull_valid & (df["close"].ge(bull_low)) & (df["close"].le(bull_high)) & (pos_in_bull_gap <= self.htf_fvg_touch_ratio)
                df.loc[(df["enter_long"] == 1) & bull_valid & ~long_fvg_ok, "enter_long"] = 0

                bear_valid = bear_low.notna() & bear_high.notna() & (bear_age <= self.htf_fvg_max_age)
                gap_height_bear = (bear_high - bear_low)
                pos_in_bear_gap = (df["close"] - bear_low) / gap_height_bear.replace(0, pd.NA)
                short_fvg_ok = bear_valid & (df["close"].ge(bear_low)) & (df["close"].le(bear_high)) & (pos_in_bear_gap >= (1 - self.htf_fvg_touch_ratio))
                df.loc[(df["enter_short"] == 1) & bear_valid & ~short_fvg_ok, "enter_short"] = 0

                # Tagging
                if "entry_tag" not in df.columns:
                    df["entry_tag"] = ""
                df.loc[(df["enter_long"] == 1) & long_fvg_ok, "entry_tag"] = "HTF_BULL_FVG"
                df.loc[(df["enter_short"] == 1) & short_fvg_ok, "entry_tag"] = "HTF_BEAR_FVG"

        # Final snapshot after FVG filter
        df["enter_long_after_fvg"] = df["enter_long"]
        df["enter_short_after_fvg"] = df["enter_short"]

        # Lightweight pruning diagnostics logging (last row only)
        try:
            if metadata and "pair" in metadata and len(df) > 0 and hasattr(self, "config"):
                from pathlib import Path
                pair = metadata["pair"]
                ud = Path(self.config.get("user_data_dir", "user_data"))
                log_dir = ud / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "htf.prune.log"
                counts_line = (
                    f"{pair} rawL={int(df['enter_long_raw'].sum())} trendL={int(df['enter_long_after_trend'].sum())} fvgL={int(df['enter_long_after_fvg'].sum())} "
                    f"rawS={int(df['enter_short_raw'].sum())} trendS={int(df['enter_short_after_trend'].sum())} fvgS={int(df['enter_short_after_fvg'].sum())}\n"
                )
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(counts_line)
        except Exception:
            pass

        return df

    # Disable target/invalidation exits from base by forcing no signal exits
    def populate_exit_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        if "exit_long" not in df.columns:
            df["exit_long"] = 0
        else:
            df["exit_long"] = 0
        if "exit_short" not in df.columns:
            df["exit_short"] = 0
        else:
            df["exit_short"] = 0
        return df

    # Futures leverage selection
    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        try:
            # Prefer explicit per-side overrides
            side_norm = (side or "").lower()
            target = self.default_leverage
            if side_norm == "long" and self.long_leverage is not None:
                target = float(self.long_leverage)
            elif side_norm == "short" and self.short_leverage is not None:
                target = float(self.short_leverage)
            # Fallback to futures_leverage if provided
            if getattr(self, "futures_leverage", None) is not None:
                target = float(self.futures_leverage)
            # As last resort use proposed leverage
            if target is None:
                target = float(proposed_leverage)
            # Apply optional config cap then exchange cap
            if self.max_config_leverage is not None:
                target = min(target, float(self.max_config_leverage))
            target = min(float(target), float(max_leverage))
            if target < 1.0:
                target = 1.0
            return float(target)
        except Exception:
            return float(min(max(1.0, proposed_leverage), max_leverage))

    # Exit only on profit
    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> Optional[str]:
        try:
            # current_profit is in ratio form: 1.0 = 100%, so check > 0.5 for >50% profit
            if current_profit is not None and float(current_profit) > 0.5:
                return "PROFIT_ONLY"
            return None
        except Exception:
            return None

    # Liquidation-based DCA logic
    def _calculate_liquidation_price(self, trade: Any, current_rate: float) -> Optional[float]:
        """Calculate liquidation price based on average entry, leverage, and position side."""
        try:
            # Get average entry price (updated after each DCA)
            avg_entry = float(getattr(trade, "open_rate", current_rate) or current_rate)
            
            # Get effective leverage for this trade
            leverage = float(getattr(trade, "leverage", self.default_leverage) or self.default_leverage)
            if leverage < 1.0:
                leverage = self.default_leverage
            
            # Determine position direction
            is_short = bool(getattr(trade, "is_short", False))
            
            # Calculate liquidation price
            # For longs: liq_price = entry × (1 - 1/leverage)
            # For shorts: liq_price = entry × (1 + 1/leverage)
            if is_short:
                liq_price = avg_entry * (1 + 1/leverage)
            else:
                liq_price = avg_entry * (1 - 1/leverage)
            
            return float(liq_price)
        except Exception:
            return None
    
    def _distance_to_liquidation_pct(self, current_price: float, liq_price: float, is_short: bool) -> float:
        """Calculate distance from current price to liquidation as percentage."""
        try:
            if is_short:
                # For shorts: distance = (liq_price - current_price) / current_price × 100
                # Positive = safe, negative = beyond liquidation
                distance_pct = (liq_price - current_price) / current_price * 100.0
            else:
                # For longs: distance = (current_price - liq_price) / current_price × 100
                # Positive = safe, negative = beyond liquidation
                distance_pct = (current_price - liq_price) / current_price * 100.0
            
            return float(distance_pct)
        except Exception:
            return 0.0

    def adjust_trade_position(
        self,
        trade: Any,
        current_rate: float,
        current_profit: float,
        min_stake: float,
        max_stake: float,
        **kwargs: Any,
    ) -> Optional[float]:
        try:
            # Only add when underwater
            if float(current_profit or 0.0) >= 0.0:
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "not_underwater"
                    trade.user_data = ud
                except Exception:
                    pass
                return None
            
            # 🔥 COOLDOWN CHECK: Prevent rapid-fire DCAs
            try:
                ud = dict(getattr(trade, "user_data", {}) or {})
                last_dca_time = ud.get("last_dca_timestamp")
                if last_dca_time is not None:
                    from datetime import datetime, timedelta
                    last_dca_dt = datetime.fromisoformat(str(last_dca_time))
                    now = datetime.utcnow()
                    minutes_since_last_dca = (now - last_dca_dt).total_seconds() / 60.0
                    if minutes_since_last_dca < self.dca_cooldown_minutes:
                        try:
                            ud["dca_skip_reason"] = "cooldown_active"
                            ud["minutes_since_last_dca"] = float(minutes_since_last_dca)
                            ud["cooldown_required"] = float(self.dca_cooldown_minutes)
                            trade.user_data = ud
                        except Exception:
                            pass
                        return None
            except Exception:
                pass  # First DCA or error parsing timestamp - allow it
            
            # Check if max adds reached
            n_entries = getattr(trade, "nr_of_successful_entries", None)
            if n_entries is not None:
                adds_done = max(0, int(n_entries) - 1)
            else:
                adds_done = int(getattr(trade, "nr_of_buys", 0))
            
            if adds_done >= self.dca_max_adds:
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "max_adds_reached"
                    trade.user_data = ud
                except Exception:
                    pass
                return None
            
            # Calculate liquidation price
            liq_price = self._calculate_liquidation_price(trade, current_rate)
            if liq_price is None:
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "cannot_calculate_liquidation"
                    trade.user_data = ud
                except Exception:
                    pass
                return None
            
            # Get position direction
            is_short = bool(getattr(trade, "is_short", False))
            
            # Calculate distance to liquidation
            distance_pct = self._distance_to_liquidation_pct(current_rate, liq_price, is_short)
            
            # Trigger DCA if within buffer zone
            if distance_pct > self.dca_liq_buffer_pct:
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "not_close_to_liquidation"
                    ud["distance_to_liq_pct"] = float(distance_pct)
                    ud["liq_buffer_needed"] = float(self.dca_liq_buffer_pct)
                    ud["liquidation_price"] = float(liq_price)
                    trade.user_data = ud
                except Exception:
                    pass
                return None

            # Use modern entries count when available; convert to DCA adds
            n_entries = getattr(trade, "nr_of_successful_entries", None)
            if n_entries is not None:
                adds_done = max(0, int(n_entries) - 1)
            else:
                adds_done = int(getattr(trade, "nr_of_buys", 0))
            base_stake = float(getattr(trade, "stake_amount", min_stake))
            if self.dca_mode == "martingale":
                stake = base_stake * (2 ** adds_done)
            else:
                stake = base_stake

            # Enforce per-trade budget cap using margin (stake), not notional.
            # Futures: use trade.stake_amount as base margin and track cumulative DCA margin via user_data.
            try:
                base_margin = float(getattr(trade, "stake_amount", 0.0) or 0.0)
            except Exception:
                base_margin = 0.0
            try:
                ud_tmp = dict(getattr(trade, "user_data", {}) or {})
                dca_margin_used = float(ud_tmp.get("dca_margin_used", 0.0) or 0.0)
            except Exception:
                dca_margin_used = 0.0
            invested_so_far = float(base_margin) + float(dca_margin_used)
            remaining_budget = max(0.0, float(self.dca_total_budget) - float(invested_so_far))
            if remaining_budget <= 0.0:
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "no_remaining_budget"
                    ud["remaining_budget"] = 0.0
                    ud["invested_so_far_margin"] = float(invested_so_far)
                    trade.user_data = ud
                except Exception:
                    pass
                return None
            stake = min(stake, remaining_budget)
            if stake < float(min_stake):
                try:
                    ud = dict(getattr(trade, "user_data", {}) or {})
                    ud["dca_skip_reason"] = "below_min_stake"
                    ud["remaining_budget"] = float(remaining_budget)
                    ud["min_stake"] = float(min_stake)
                    ud["candidate_stake"] = float(stake)
                    trade.user_data = ud
                except Exception:
                    pass
                return None

            # Respect engine min/max
            stake = max(min_stake, min(stake, max_stake))
            # Diagnostics: record DCA add details + timestamp for cooldown
            try:
                from datetime import datetime
                ud = dict(getattr(trade, "user_data", {}) or {})
                ud["dca_adds"] = int(ud.get("dca_adds", 0)) + 1
                ud["last_dca_stake"] = float(stake)
                ud["last_dca_timestamp"] = datetime.utcnow().isoformat()  # 🔥 Record timestamp
                ud["remaining_budget"] = float(remaining_budget)
                prev_used = float(ud.get("dca_margin_used", 0.0) or 0.0)
                ud["dca_margin_used"] = float(prev_used + float(stake))
                ud["distance_to_liq_pct"] = float(distance_pct)
                ud["liquidation_price"] = float(liq_price)
                ud["is_short"] = bool(is_short)
                trade.user_data = ud
            except Exception:
                pass
            return float(stake)
        except Exception:
            return None

    # Ensure initial stake does not exceed budget
    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        **kwargs: Any,
    ) -> float:
        try:
            # Use proposed stake from config (e.g., 500), capped to total budget
            # Never default to full budget for initial stake!
            ps = float(proposed_stake)
            cap = float(self.dca_total_budget)
            return float(min(ps, cap))
        except Exception:
            return float(proposed_stake)
