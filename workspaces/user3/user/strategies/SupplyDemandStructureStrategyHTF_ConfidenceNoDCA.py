from typing import Any, Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.strategy import stoploss_from_absolute
except Exception:  # Allows local linting outside Freqtrade
    stoploss_from_absolute = None

from V3 import V3


class SupplyDemandStructureStrategyHTF_ConfidenceNoDCA(V3):
    """
    Supply/Demand + HTF Trend/FVG strategy with risk-managed exits and NO DCA.

    Design goals:
      - Keep your original V3 supply/demand + structure entries.
      - Keep the TrendV2 1h HTF trend filter and HTF FVG pullback filter.
      - Remove liquidation/martingale DCA completely.
      - Give the initial stop more room: structure zone edge +/- 2x ATR.
      - Add confidence scoring and filter weak setups.
      - Move stop to breakeven after +1R.
      - Start ATR trailing after +2R.
      - Take profit around +3R, while still allowing V3 structure exits.

    Timeframe:
      - Default inherits V3 timeframe = "15m".
      - To test 5m, uncomment the two lines below. 5m will produce more signals,
        but more noise. Keep the 1h informative filter enabled.
    """

    strategy_name = "SupplyDemandStructureStrategyHTF_ConfidenceNoDCA"

    # --- Optional 5m test ---
    # timeframe = "5m"
    # pivot_lookback = 36

    can_short = True

    # --- Risk / exits ---
    use_custom_stoploss = True
    use_exit_signal = True
    ignore_roi_if_entry_signal = False
    minimal_roi = {"0": 10.0}     # Keep ROI out of the way; use custom_exit/SL/signals.
    stoploss = -0.35              # Emergency fail-safe only.

    # --- No DCA ---
    position_adjustment_enable = False
    max_entry_position_adjustment = 0
    dca_enable = False

    # --- Futures leverage ---
    default_leverage: float = 3.0
    long_leverage: Optional[float] = None
    short_leverage: Optional[float] = None
    max_config_leverage: Optional[float] = 3.0
    futures_leverage: Optional[float] = None

    max_open_trades = 10

    # Base RR filtering inherited by V3, slightly stricter than your original.
    rr_min = 1.2
    rr_min_low_vol = 1.0
    rr_min_high_vol = 1.5

    # --- HTF FVG filter ---
    use_htf_fvg: bool = True
    htf_fvg_max_age: int = 48          # 1h candles
    htf_fvg_touch_ratio: float = 0.35  # Longs near lower gap area, shorts near upper gap area.

    # --- Structure + ATR stop ---
    stop_atr_buffer_mult: float = 2.0  # Requested: stop = structure edge +/- 2x ATR.
    min_initial_risk_pct: float = 0.002
    max_initial_risk_pct: float = 0.15  # Skip impossible/wild risk calculations in custom SL.

    # --- R-based management ---
    breakeven_at_r: float = 1.0
    trail_start_r: float = 2.0
    atr_trail_mult: float = 2.0
    take_profit_r: float = 3.0

    # --- Confidence scoring ---
    min_confidence: int = 55          # Minimum confidence to allow an entry.
    high_confidence: int = 75         # Used for tagging/logging.
    confidence_log: bool = True

    # Weights sum to 100.
    weight_htf_trend: int = 20
    weight_htf_fvg: int = 20
    weight_zone_quality: int = 20
    weight_rr: int = 20
    weight_candle_confirm: int = 10
    weight_volatility: int = 10

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    def _last_analyzed_df(self, pair: str) -> Optional[DataFrame]:
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
        Entry-time risk model.

        Long stop  = entry-time zone_low  - 2x ATR
        Short stop = entry-time zone_high + 2x ATR
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

            atr = pd.to_numeric(pd.Series([entry_row.get("atr")]), errors="coerce").iloc[0]
            if not pd.notna(atr) or float(atr) <= 0:
                atr = entry * 0.005
            atr = float(atr)

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
        try:
            is_short = bool(getattr(trade, "is_short", False))
            leverage = float(getattr(trade, "leverage", 1.0) or 1.0)

            if stoploss_from_absolute is not None:
                try:
                    return float(stoploss_from_absolute(
                        stop_price,
                        current_rate=current_rate,
                        is_short=is_short,
                        leverage=leverage,
                    ))
                except TypeError:
                    return float(stoploss_from_absolute(
                        stop_price,
                        current_rate=current_rate,
                        is_short=is_short,
                    ))

            # Fallback approximation for local linting outside Freqtrade.
            if is_short:
                risk = (float(stop_price) - float(current_rate)) / float(current_rate)
            else:
                risk = (float(current_rate) - float(stop_price)) / float(current_rate)
            return -abs(float(risk) * leverage)
        except Exception:
            return self.stoploss

    # ------------------------------------------------------------------
    # Confidence scoring
    # ------------------------------------------------------------------
    def _add_confidence_score(self, df: DataFrame) -> DataFrame:
        """Adds confidence_score and confidence_level columns for every candle."""
        htf_suffix = f"_{self.informative_timeframe}"
        trend_col = f"htf_trend{htf_suffix}"
        bull_low_col = f"htf_bull_fvg_low{htf_suffix}"
        bull_high_col = f"htf_bull_fvg_high{htf_suffix}"
        bull_age_col = f"htf_bull_fvg_age{htf_suffix}"
        bear_low_col = f"htf_bear_fvg_low{htf_suffix}"
        bear_high_col = f"htf_bear_fvg_high{htf_suffix}"
        bear_age_col = f"htf_bear_fvg_age{htf_suffix}"

        score = pd.Series(0.0, index=df.index)

        # 1) HTF trend alignment.
        if trend_col in df.columns:
            trend_score = np.where(
                ((df.get("enter_long", 0) == 1) & (df[trend_col] == "UP")) |
                ((df.get("enter_short", 0) == 1) & (df[trend_col] == "DOWN")),
                self.weight_htf_trend,
                0,
            )
            score += pd.Series(trend_score, index=df.index)

        # 2) HTF FVG quality: fresher gap = better, price deeper in preferred side = better.
        fvg_score = pd.Series(0.0, index=df.index)
        if {bull_low_col, bull_high_col, bull_age_col, bear_low_col, bear_high_col, bear_age_col}.issubset(df.columns):
            bull_low = pd.to_numeric(df[bull_low_col], errors="coerce")
            bull_high = pd.to_numeric(df[bull_high_col], errors="coerce")
            bull_age = pd.to_numeric(df[bull_age_col], errors="coerce")
            bear_low = pd.to_numeric(df[bear_low_col], errors="coerce")
            bear_high = pd.to_numeric(df[bear_high_col], errors="coerce")
            bear_age = pd.to_numeric(df[bear_age_col], errors="coerce")

            bull_height = (bull_high - bull_low).replace(0, pd.NA)
            bear_height = (bear_high - bear_low).replace(0, pd.NA)
            bull_pos = ((df["close"] - bull_low) / bull_height).clip(lower=0, upper=1)
            bear_pos = ((df["close"] - bear_low) / bear_height).clip(lower=0, upper=1)

            bull_fresh = (1 - (bull_age / self.htf_fvg_max_age)).clip(lower=0, upper=1)
            bear_fresh = (1 - (bear_age / self.htf_fvg_max_age)).clip(lower=0, upper=1)

            # Longs prefer lower part of bullish FVG. Shorts prefer upper part of bearish FVG.
            bull_quality = ((1 - bull_pos) * 0.6 + bull_fresh * 0.4) * self.weight_htf_fvg
            bear_quality = (bear_pos * 0.6 + bear_fresh * 0.4) * self.weight_htf_fvg

            fvg_score = pd.Series(
                np.where(df.get("enter_long", 0) == 1, bull_quality.fillna(0),
                         np.where(df.get("enter_short", 0) == 1, bear_quality.fillna(0), 0)),
                index=df.index,
            )
        score += fvg_score

        # 3) Zone quality: zone size around 0.5-3 ATR and relatively fresh.
        zl = pd.to_numeric(df.get("zone_low"), errors="coerce")
        zh = pd.to_numeric(df.get("zone_high"), errors="coerce")
        atr = pd.to_numeric(df.get("atr"), errors="coerce")
        zone_age = pd.to_numeric(df.get("zone_age"), errors="coerce")
        zone_size = (zh - zl).abs()
        ratio = (zone_size / atr.replace(0, pd.NA)).replace([np.inf, -np.inf], np.nan)
        size_quality = np.where((ratio >= 0.5) & (ratio <= 3.0), 1.0,
                                np.where((ratio >= 0.25) & (ratio <= 5.0), 0.6, 0.2))
        age_quality = (1 - (zone_age / float(self.zone_expiry))).clip(lower=0, upper=1).fillna(0.5)
        zone_quality = (pd.Series(size_quality, index=df.index).fillna(0) * 0.6 + age_quality * 0.4)
        score += zone_quality * self.weight_zone_quality

        # 4) RR quality based on target vs wider 2xATR stop.
        th = pd.to_numeric(df.get("target_high"), errors="coerce")
        tl = pd.to_numeric(df.get("target_low"), errors="coerce")
        long_stop = zl - atr * self.stop_atr_buffer_mult
        short_stop = zh + atr * self.stop_atr_buffer_mult
        long_risk = (df["close"] - long_stop).replace(0, pd.NA)
        short_risk = (short_stop - df["close"]).replace(0, pd.NA)
        long_reward = th - df["close"]
        short_reward = df["close"] - tl
        long_rr = (long_reward / long_risk).replace([np.inf, -np.inf], np.nan)
        short_rr = (short_reward / short_risk).replace([np.inf, -np.inf], np.nan)
        rr = pd.Series(np.where(df.get("enter_long", 0) == 1, long_rr, np.where(df.get("enter_short", 0) == 1, short_rr, np.nan)), index=df.index)
        rr_quality = (rr / self.take_profit_r).clip(lower=0, upper=1).fillna(0)
        score += rr_quality * self.weight_rr

        # 5) Candle confirmation.
        bull_confirm = (df["close"] > df["open"]) & (df["close"] > df["close"].shift(1))
        bear_confirm = (df["close"] < df["open"]) & (df["close"] < df["close"].shift(1))
        confirm = ((df.get("enter_long", 0) == 1) & bull_confirm) | ((df.get("enter_short", 0) == 1) & bear_confirm)
        score += confirm.astype(float) * self.weight_candle_confirm

        # 6) Volatility quality: avoid extremely dead/extremely wild candles.
        atr_pct = (atr / df["close"]).replace([np.inf, -np.inf], np.nan)
        vol_quality = np.where((atr_pct >= 0.003) & (atr_pct <= 0.03), 1.0,
                               np.where((atr_pct >= 0.0015) & (atr_pct <= 0.05), 0.5, 0.0))
        score += pd.Series(vol_quality, index=df.index).fillna(0) * self.weight_volatility

        df["confidence_score"] = score.clip(lower=0, upper=100).round(1)
        df["confidence_level"] = np.where(
            df["confidence_score"] >= self.high_confidence,
            "HIGH",
            np.where(df["confidence_score"] >= self.min_confidence, "MEDIUM", "LOW"),
        )
        return df

    # ------------------------------------------------------------------
    # Entries: V3 base + HTF trend + HTF FVG + confidence filter.
    # ------------------------------------------------------------------
    def populate_entry_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        df = super().populate_entry_trend(df, metadata)

        if "entry_tag" not in df.columns:
            df["entry_tag"] = ""

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

        # If HTF did not merge, keep base signals but confidence will likely filter most out.
        if trend_col in df.columns:
            df.loc[(df["enter_long"] == 1) & (df[trend_col] != "UP"), "enter_long"] = 0
            df.loc[(df["enter_short"] == 1) & (df[trend_col] != "DOWN"), "enter_short"] = 0

        df["enter_long_after_trend"] = df["enter_long"]
        df["enter_short_after_trend"] = df["enter_short"]

        # HTF FVG filter.
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
                long_fvg_ok = bull_valid & df["close"].ge(bull_low) & df["close"].le(bull_high) & (pos_in_bull_gap <= self.htf_fvg_touch_ratio)
                df.loc[(df["enter_long"] == 1) & bull_valid & ~long_fvg_ok, "enter_long"] = 0

                bear_valid = bear_low.notna() & bear_high.notna() & (bear_age <= self.htf_fvg_max_age)
                bear_gap_height = (bear_high - bear_low).replace(0, pd.NA)
                pos_in_bear_gap = (df["close"] - bear_low) / bear_gap_height
                short_fvg_ok = bear_valid & df["close"].ge(bear_low) & df["close"].le(bear_high) & (pos_in_bear_gap >= (1 - self.htf_fvg_touch_ratio))
                df.loc[(df["enter_short"] == 1) & bear_valid & ~short_fvg_ok, "enter_short"] = 0

        df["enter_long_after_fvg"] = df["enter_long"]
        df["enter_short_after_fvg"] = df["enter_short"]

        # Confidence score after HTF/FVG filters, then reject weak setups.
        df = self._add_confidence_score(df)
        df.loc[(df["enter_long"] == 1) & (df["confidence_score"] < self.min_confidence), "enter_long"] = 0
        df.loc[(df["enter_short"] == 1) & (df["confidence_score"] < self.min_confidence), "enter_short"] = 0

        # Tag entries with confidence level.
        df.loc[df["enter_long"] == 1, "entry_tag"] = "LONG_CONF_" + df.loc[df["enter_long"] == 1, "confidence_level"].astype(str)
        df.loc[df["enter_short"] == 1, "entry_tag"] = "SHORT_CONF_" + df.loc[df["enter_short"] == 1, "confidence_level"].astype(str)

        if self.confidence_log:
            self._log_confidence_pruning(df, metadata)

        return df

    def _log_confidence_pruning(self, df: DataFrame, metadata: Dict[str, Any] | None) -> None:
        try:
            if not metadata or "pair" not in metadata or not hasattr(self, "config"):
                return
            from pathlib import Path
            pair = metadata["pair"]
            ud = Path(self.config.get("user_data_dir", "user_data"))
            log_dir = ud / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "confidence.prune.log"
            line = (
                f"{datetime.utcnow().isoformat()} {pair} "
                f"rawL={int(df['enter_long_raw'].sum())} trendL={int(df['enter_long_after_trend'].sum())} "
                f"fvgL={int(df['enter_long_after_fvg'].sum())} finalL={int(df['enter_long'].sum())} "
                f"rawS={int(df['enter_short_raw'].sum())} trendS={int(df['enter_short_after_trend'].sum())} "
                f"fvgS={int(df['enter_short_after_fvg'].sum())} finalS={int(df['enter_short'].sum())} "
                f"avgConf={float(df['confidence_score'].replace(0, np.nan).mean() or 0):.1f}\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Exit signals: keep V3 structure exits active.
    # ------------------------------------------------------------------
    def populate_exit_trend(self, df: DataFrame, metadata: Dict[str, Any] | None = None) -> DataFrame:
        return super().populate_exit_trend(df, metadata)

    # ------------------------------------------------------------------
    # Leverage selection.
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
    # Custom stoploss: structure + 2xATR, BE at +1R, trail after +2R.
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

        # Breakeven after +1R. Small cushion to cover noise/fees.
        if r_mult is not None and r_mult >= self.breakeven_at_r:
            entry = info["entry"]
            stop_price = entry * (0.999 if is_short else 1.001)

        # ATR trailing after +2R.
        if r_mult is not None and r_mult >= self.trail_start_r:
            atr = info["atr"]
            if is_short:
                trail_stop = float(current_rate) + atr * self.atr_trail_mult
                # For shorts, lower stop is tighter, but must stay above current rate.
                stop_price = min(stop_price, trail_stop) if stop_price > float(current_rate) else trail_stop
            else:
                trail_stop = float(current_rate) - atr * self.atr_trail_mult
                # For longs, higher stop is tighter, but must stay below current rate.
                stop_price = max(stop_price, trail_stop) if stop_price < float(current_rate) else trail_stop

        return self._stoploss_from_stop_price(trade, current_rate, stop_price)

    # ------------------------------------------------------------------
    # Custom exit: take full profit near +3R.
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
            if not info:
                return None
            r_mult = self._current_r_multiple(trade, current_rate, info["risk_abs"])
            if r_mult is not None and r_mult >= self.take_profit_r:
                return f"TAKE_PROFIT_{self.take_profit_r:.1f}R"
            return None
        except Exception:
            return None

    # Explicitly disable DCA/position adjustment.
    def adjust_trade_position(self, *args: Any, **kwargs: Any) -> Optional[float]:
        return None
