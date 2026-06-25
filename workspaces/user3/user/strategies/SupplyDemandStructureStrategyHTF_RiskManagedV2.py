from typing import Any, Dict, Optional, List
from datetime import datetime

import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.strategy import stoploss_from_absolute
except Exception:  # Allows local linting outside freqtrade
    stoploss_from_absolute = None

from V3 import V3


class SupplyDemandStructureStrategyHTF_RiskManagedV2(V3):
    """
    Risk-managed test version of SupplyDemandStructureStrategyHTF_TrendV2.

    What changed vs your original TrendV2:
      - Lower default leverage: 3x instead of 10x.
      - Real custom stoploss enabled.
      - Stop is based on entry-time structure zone + ATR buffer.
      - Breakeven once trade reaches +1R.
      - ATR trailing after +2R.
      - No liquidation/martingale DCA.
      - Limited uniform DCA at predefined adverse movement: about -1R and -2R.
      - Exit is no longer only at +50%; it exits on R-based profit or structure failure.
      - Keeps your 1h HTF trend + FVG filter from TrendV2.

    Timeframe note:
      - Default is inherited from V3: 15m.
      - To test aggressive execution, set timeframe = "5m" below and reduce pivot_lookback.
      - True 15m-zone + 5m-trigger requires a separate 15m informative merge.
    """

    strategy_name = "SupplyDemandStructureStrategyHTF_RiskManagedV2"

    # --- Timeframe ---
    # Start with 15m. For a 5m experiment, uncomment both lines:
    # timeframe = "5m"
    # pivot_lookback = 36

    can_short = True
    use_custom_stoploss = True
    use_exit_signal = True
    position_adjustment_enable = True

    # Keep ROI out of the way; exits are handled by custom_exit / exit signals / stoploss.
    minimal_roi = {"0": 10.0}

    # Emergency fail-safe only. The real stop is custom_stoploss.
    stoploss = -0.35

    # More realistic leverage for futures testing.
    default_leverage: float = 3.0
    long_leverage: Optional[float] = None
    short_leverage: Optional[float] = None
    max_config_leverage: Optional[float] = 3.0
    futures_leverage: Optional[float] = None

    max_open_trades = 10
    max_entry_position_adjustment = 2

    # Keep trend participation possible, but don't accept terrible asymmetry.
    rr_min = 1.2
    rr_min_low_vol = 1.0
    rr_min_high_vol = 1.5

    # HTF Fair Value Gap filters, same idea as your TrendV2.
    use_htf_fvg: bool = True
    htf_fvg_max_age: int = 48
    htf_fvg_touch_ratio: float = 0.35

    # --- Structure/ATR stop settings ---
    # Initial stop = zone edge +/- ATR buffer.
    stop_atr_buffer_mult: float = 0.35
    max_initial_risk_pct: float = 0.08   # reject/ignore weird stops above 8% distance
    min_initial_risk_pct: float = 0.002  # avoid microscopic invalid stops

    # Breakeven and trailing.
    breakeven_at_r: float = 1.0
    trail_start_r: float = 2.0
    atr_trail_mult: float = 2.0

    # Profit taking / exit management.
    take_profit_r: float = 3.0
    profit_floor_pct: float = 0.03  # allow at least +3% profit exit if R cannot be computed

    # --- Safer DCA ---
    dca_enable: bool = True
    dca_mode: str = "uniform"
    dca_max_adds: int = 2
    dca_total_budget: float = 2500.0
    dca_cooldown_minutes: int = 30
    dca_stake_multiplier: float = 1.0
    dca_trigger_r_levels: List[float] = [1.0, 2.0]  # DCA near -1R and -2R adverse move

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _last_analyzed_df(self, pair: str) -> Optional[DataFrame]:
        """Use cached dataframe from V3.populate_indicators, falling back to dp if possible."""
        df = getattr(self, "_df_cache", {}).get((pair, self.timeframe))
        if df is not None and not df.empty:
            return df.sort_index()

        try:
            if hasattr(self, "dp") and self.dp:
                analyzed, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
                if analyzed is not None and not analyzed.empty:
                    return analyzed.sort_index()
        except Exception:
            pass
        return None

    def _row_at_or_before(self, df: DataFrame, when: datetime) -> Optional[pd.Series]:
        try:
            if "date" in df.columns:
                dff = df.copy()
                dff["date"] = pd.to_datetime(dff["date"], utc=True, errors="coerce")
                ts = pd.Timestamp(when)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                rows = dff[dff["date"] <= ts]
                if not rows.empty:
                    return rows.iloc[-1]
            return df.loc[:when].iloc[-1]
        except Exception:
            try:
                return df.iloc[-1]
            except Exception:
                return None

    def _trade_risk_info(self, pair: str, trade: Any) -> Optional[Dict[str, float]]:
        """
        Calculate entry-time 1R using structure zone edge plus ATR buffer.

        Long stop:  zone_low - ATR * buffer
        Short stop: zone_high + ATR * buffer
        """
        df = self._last_analyzed_df(pair)
        if df is None or df.empty:
            return None

        entry_time = getattr(trade, "open_date_utc", None) or getattr(trade, "open_date", None)
        entry_row = self._row_at_or_before(df, entry_time) if entry_time else None
        if entry_row is None:
            return None

        try:
            entry = float(getattr(trade, "open_rate"))
            is_short = bool(getattr(trade, "is_short", False))
            atr = float(pd.to_numeric(pd.Series([entry_row.get("atr")]), errors="coerce").iloc[0])
            if not pd.notna(atr) or atr <= 0:
                atr = entry * 0.005

            if is_short:
                zone_edge = pd.to_numeric(pd.Series([entry_row.get("zone_high")]), errors="coerce").iloc[0]
                if not pd.notna(zone_edge):
                    return None
                stop_price = float(zone_edge) + atr * self.stop_atr_buffer_mult
                risk_abs = stop_price - entry
            else:
                zone_edge = pd.to_numeric(pd.Series([entry_row.get("zone_low")]), errors="coerce").iloc[0]
                if not pd.notna(zone_edge):
                    return None
                stop_price = float(zone_edge) - atr * self.stop_atr_buffer_mult
                risk_abs = entry - stop_price

            if risk_abs <= 0:
                return None
            risk_pct = risk_abs / entry
            if risk_pct < self.min_initial_risk_pct or risk_pct > self.max_initial_risk_pct:
                return None

            return {
                "entry": float(entry),
                "stop_price": float(stop_price),
                "risk_abs": float(risk_abs),
                "risk_pct": float(risk_pct),
                "atr": float(atr),
                "is_short": 1.0 if is_short else 0.0,
            }
        except Exception:
            return None

    def _current_r_multiple(self, trade: Any, current_rate: float, risk_abs: float) -> Optional[float]:
        try:
            entry = float(getattr(trade, "open_rate"))
            if risk_abs <= 0:
                return None
            if bool(getattr(trade, "is_short", False)):
                return (entry - float(current_rate)) / risk_abs
            return (float(current_rate) - entry) / risk_abs
        except Exception:
            return None

    def _stoploss_from_stop_price(self, trade: Any, current_rate: float, stop_price: float) -> float:
        """Convert an absolute stop price into Freqtrade custom_stoploss format."""
        try:
            is_short = bool(getattr(trade, "is_short", False))
            leverage = float(getattr(trade, "leverage", 1.0) or 1.0)

            if stoploss_from_absolute is not None:
                return float(stoploss_from_absolute(
                    stop_price,
                    current_rate=current_rate,
                    is_short=is_short,
                    leverage=leverage,
                ))

            # Fallback approximation if imported outside Freqtrade.
            if is_short:
                risk = (float(stop_price) - float(current_rate)) / float(current_rate)
            else:
                risk = (float(current_rate) - float(stop_price)) / float(current_rate)
            return -abs(float(risk) * leverage)
        except Exception:
            return self.stoploss

    # ------------------------------------------------------------------
    # Entries: base V3 + HTF trend + HTF FVG, with slightly stricter tagging.
    # ------------------------------------------------------------------
    def populate_entry_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        df = super().populate_entry_trend(df, metadata)

        df["enter_long_raw"] = df.get("enter_long", 0)
        df["enter_short_raw"] = df.get("enter_short", 0)

        htf_suffix = f"_{self.informative_timeframe}"
        trend_col = f"htf_trend{htf_suffix}"
        bull_low_col = f"htf_bull_fvg_low{htf_suffix}"
        bull_high_col = f"htf_bull_fvg_high{htf_suffix}"
        bull_age_col = f"htf_bull_fvg_age{htf_suffix}"
        bear_low_col = f"htf_bear_fvg_low{htf_suffix}"
        bear_high_col = f"htf_bear_fvg_high{htf_suffix}"
        bear_age_col = f"htf_bear_fvg_age{htf_suffix}"

        if trend_col not in df.columns:
            return df

        htf_trend = df[trend_col]
        df.loc[(df["enter_long"] == 1) & (htf_trend != "UP"), "enter_long"] = 0
        df.loc[(df["enter_short"] == 1) & (htf_trend != "DOWN"), "enter_short"] = 0

        df["enter_long_after_trend"] = df["enter_long"]
        df["enter_short_after_trend"] = df["enter_short"]

        if "entry_tag" not in df.columns:
            df["entry_tag"] = ""

        if self.use_htf_fvg:
            required = {bull_low_col, bull_high_col, bull_age_col, bear_low_col, bear_high_col, bear_age_col}
            if required.issubset(df.columns):
                bull_low = pd.to_numeric(df[bull_low_col], errors="coerce")
                bull_high = pd.to_numeric(df[bull_high_col], errors="coerce")
                bull_age = pd.to_numeric(df[bull_age_col], errors="coerce")
                bear_low = pd.to_numeric(df[bear_low_col], errors="coerce")
                bear_high = pd.to_numeric(df[bear_high_col], errors="coerce")
                bear_age = pd.to_numeric(df[bear_age_col], errors="coerce")

                bull_valid = bull_low.notna() & bull_high.notna() & (bull_age <= self.htf_fvg_max_age)
                bull_gap_height = (bull_high - bull_low).replace(0, pd.NA)
                pos_in_bull_gap = (df["close"] - bull_low) / bull_gap_height
                long_fvg_ok = (
                    bull_valid &
                    df["close"].ge(bull_low) &
                    df["close"].le(bull_high) &
                    (pos_in_bull_gap <= self.htf_fvg_touch_ratio)
                )
                df.loc[(df["enter_long"] == 1) & bull_valid & ~long_fvg_ok, "enter_long"] = 0

                bear_valid = bear_low.notna() & bear_high.notna() & (bear_age <= self.htf_fvg_max_age)
                bear_gap_height = (bear_high - bear_low).replace(0, pd.NA)
                pos_in_bear_gap = (df["close"] - bear_low) / bear_gap_height
                short_fvg_ok = (
                    bear_valid &
                    df["close"].ge(bear_low) &
                    df["close"].le(bear_high) &
                    (pos_in_bear_gap >= (1 - self.htf_fvg_touch_ratio))
                )
                df.loc[(df["enter_short"] == 1) & bear_valid & ~short_fvg_ok, "enter_short"] = 0

                df.loc[(df["enter_long"] == 1) & long_fvg_ok, "entry_tag"] = "HTF_BULL_FVG_RISK_MANAGED"
                df.loc[(df["enter_short"] == 1) & short_fvg_ok, "entry_tag"] = "HTF_BEAR_FVG_RISK_MANAGED"

        # Optional current-timeframe confirmation. This is useful especially if you test timeframe="5m".
        # Long: close above previous close and candle body is positive.
        # Short: close below previous close and candle body is negative.
        bullish_confirm = (df["close"] > df["open"]) & (df["close"] > df["close"].shift(1))
        bearish_confirm = (df["close"] < df["open"]) & (df["close"] < df["close"].shift(1))
        df.loc[(df["enter_long"] == 1) & ~bullish_confirm, "enter_long"] = 0
        df.loc[(df["enter_short"] == 1) & ~bearish_confirm, "enter_short"] = 0

        df["enter_long_after_fvg_confirm"] = df["enter_long"]
        df["enter_short_after_fvg_confirm"] = df["enter_short"]

        return df

    # ------------------------------------------------------------------
    # Exit signals: re-enable V3 structure exits instead of suppressing them.
    # ------------------------------------------------------------------
    def populate_exit_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        return super().populate_exit_trend(df, metadata)

    # ------------------------------------------------------------------
    # Futures leverage selection.
    # ------------------------------------------------------------------
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
            side_norm = (side or "").lower()
            target = self.default_leverage
            if side_norm == "long" and self.long_leverage is not None:
                target = float(self.long_leverage)
            elif side_norm == "short" and self.short_leverage is not None:
                target = float(self.short_leverage)
            if self.futures_leverage is not None:
                target = float(self.futures_leverage)
            if self.max_config_leverage is not None:
                target = min(float(target), float(self.max_config_leverage))
            target = min(float(target), float(max_leverage))
            return float(max(1.0, target))
        except Exception:
            return float(min(max(1.0, proposed_leverage), max_leverage))

    # ------------------------------------------------------------------
    # Custom stoploss: initial structure stop, BE at +1R, ATR trail after +2R.
    # ------------------------------------------------------------------
    def custom_stoploss(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> float:
        info = self._trade_risk_info(pair, trade)
        if not info:
            return self.stoploss

        is_short = bool(getattr(trade, "is_short", False))
        r_mult = self._current_r_multiple(trade, current_rate, info["risk_abs"])
        stop_price = info["stop_price"]

        # Breakeven after +1R.
        if r_mult is not None and r_mult >= self.breakeven_at_r:
            entry = info["entry"]
            # Add tiny fee/slippage cushion.
            stop_price = entry * (0.999 if is_short else 1.001)

        # ATR trailing after +2R.
        if r_mult is not None and r_mult >= self.trail_start_r:
            atr = info["atr"]
            if is_short:
                trail_stop = float(current_rate) + atr * self.atr_trail_mult
                stop_price = min(stop_price, trail_stop) if stop_price > float(current_rate) else trail_stop
            else:
                trail_stop = float(current_rate) - atr * self.atr_trail_mult
                stop_price = max(stop_price, trail_stop) if stop_price < float(current_rate) else trail_stop

        return self._stoploss_from_stop_price(trade, current_rate, stop_price)

    # ------------------------------------------------------------------
    # Custom exit: take full profit around +3R or fallback +3% if R unavailable.
    # ------------------------------------------------------------------
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
            info = self._trade_risk_info(pair, trade)
            if info:
                r_mult = self._current_r_multiple(trade, current_rate, info["risk_abs"])
                if r_mult is not None and r_mult >= self.take_profit_r:
                    return f"TAKE_PROFIT_{self.take_profit_r:.1f}R"

            if current_profit is not None and float(current_profit) >= self.profit_floor_pct:
                # Fallback only if the R model cannot resolve cleanly.
                if not info:
                    return "TAKE_PROFIT_FALLBACK"
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Safer DCA: limited uniform adds at -1R and -2R adverse movement.
    # ------------------------------------------------------------------
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
            if not self.dca_enable:
                return None
            if float(current_profit or 0.0) >= 0.0:
                return None

            pair = getattr(trade, "pair", None) or kwargs.get("pair")
            if not pair:
                return None
            info = self._trade_risk_info(pair, trade)
            if not info:
                return None

            r_mult = self._current_r_multiple(trade, current_rate, info["risk_abs"])
            if r_mult is None:
                return None

            # How many adds already happened?
            n_entries = getattr(trade, "nr_of_successful_entries", None)
            adds_done = max(0, int(n_entries) - 1) if n_entries is not None else int(getattr(trade, "nr_of_buys", 0))
            if adds_done >= self.dca_max_adds:
                return None

            # Cooldown.
            ud = dict(getattr(trade, "user_data", {}) or {})
            last_dca_time = ud.get("last_dca_timestamp")
            if last_dca_time:
                try:
                    last_dca_dt = datetime.fromisoformat(str(last_dca_time))
                    minutes_since = (datetime.utcnow() - last_dca_dt).total_seconds() / 60.0
                    if minutes_since < self.dca_cooldown_minutes:
                        ud["dca_skip_reason"] = "cooldown_active"
                        trade.user_data = ud
                        return None
                except Exception:
                    pass

            # Trigger level: first add at <= -1R, second at <= -2R by default.
            level = abs(float(self.dca_trigger_r_levels[min(adds_done, len(self.dca_trigger_r_levels) - 1)]))
            if r_mult > -level:
                ud["dca_skip_reason"] = "not_at_dca_r_level"
                ud["current_r"] = float(r_mult)
                ud["needed_r"] = float(-level)
                trade.user_data = ud
                return None

            # Enforce budget cap using margin stake.
            base_stake = float(getattr(trade, "stake_amount", min_stake) or min_stake)
            stake = base_stake * float(self.dca_stake_multiplier)

            dca_margin_used = float(ud.get("dca_margin_used", 0.0) or 0.0)
            invested_so_far = base_stake + dca_margin_used
            remaining_budget = max(0.0, float(self.dca_total_budget) - invested_so_far)
            stake = min(stake, remaining_budget, float(max_stake))

            if stake < float(min_stake):
                ud["dca_skip_reason"] = "below_min_or_no_budget"
                ud["remaining_budget"] = float(remaining_budget)
                trade.user_data = ud
                return None

            ud["dca_adds"] = int(ud.get("dca_adds", 0)) + 1
            ud["last_dca_stake"] = float(stake)
            ud["last_dca_timestamp"] = datetime.utcnow().isoformat()
            ud["dca_margin_used"] = float(dca_margin_used + stake)
            ud["dca_r_trigger"] = float(-level)
            ud["current_r"] = float(r_mult)
            trade.user_data = ud
            return float(stake)
        except Exception:
            return None

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        **kwargs: Any,
    ) -> float:
        try:
            return float(min(float(proposed_stake), float(self.dca_total_budget)))
        except Exception:
            return float(proposed_stake)
