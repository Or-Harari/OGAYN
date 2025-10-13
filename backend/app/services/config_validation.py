from __future__ import annotations

"""Validation and required key definitions for layered configs.

User-level (account) required keys (empty allowed but must exist for structural presence):
    exchange.name, exchange.key, exchange.secret
    (API credentials may remain empty while in dry_run)

Bot-level required keys (must be present; excludes all items listed under "Parameters in the strategy"):
    pair_whitelist (non-empty list at start)
    stake_currency
    stake_amount (positive float or "unlimited")
    max_open_trades (int or -1)
    dry_run (bool)
    entry_pricing.price_last_balance (float)
    entry_pricing.price_side
    exit_pricing.price_side
    (Optional but supported in bot config: tradable_balance_ratio, available_capital, amend_last_stake_amount,
     last_stake_amount_min_ratio, amount_reserve_percent, fiat_display_currency, dry_run_wallet, fee,
     futures_funding_rate, trading_mode, margin_mode, liquidation_buffer, cancel_open_orders_on_exit, custom_price_max_distance_ratio)

We treat empty strings or empty lists as "unconfigured" and raise at validation time
when starting a bot. CRUD endpoints may allow them to stay empty until launch.
"""
from typing import Any, Dict, List, Tuple

USER_REQUIRED = [
    ("exchange", "name"),
    ("exchange", "key"),
    ("exchange", "secret"),
]

BOT_REQUIRED = [
    ("pair_whitelist",),
    ("stake_currency",),
    ("stake_amount",),
    ("dry_run",),
    ("entry_pricing", "price_last_balance"),
    ("entry_pricing", "price_side"),
    ("exit_pricing", "price_side"),
    ("strategy",),
]

# Default placeholder scaffolds
USER_PLACEHOLDER = {
    "exchange": {
        "name": "binance",
        "key": "",
        "secret": "",
        "password": "",
        "sandbox": False,
    }
}

BOT_PLACEHOLDER = {
    "dry_run": True,
    "stake_currency": "USDT",
    "stake_amount": 10.0,
    "max_open_trades": 3,
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"],
    "trading_mode": "spot",
    "entry_pricing": {"price_side": "same", "price_last_balance": 0.0, "use_order_book": False, "order_book_top": 1},
    "exit_pricing": {"price_side": "same", "price_last_balance": 0.0, "use_order_book": False, "order_book_top": 1},
    "strategy": "__SET_YOUR_STRATEGY__",
}


def _dig(cfg: Dict[str, Any], path: Tuple[str, ...]):
    cur: Any = cfg
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def validate_user_config(cfg: Dict[str, Any]) -> List[str]:
    """Strict validation (legacy) used internally; mode-aware wrapper may relax this."""
    errors: List[str] = []
    for path in USER_REQUIRED:
        val = _dig(cfg, path)
        if val is None:
            errors.append(f"Missing required key: {'.'.join(path)}")
        elif isinstance(val, str) and val.strip() == "":
            errors.append(f"Empty required value: {'.'.join(path)}")
    return errors


def validate_user_config_for_mode(cfg: Dict[str, Any], mode: str | None) -> List[str]:
    """Relax credentials for non-live modes.
    - live: require non-empty key & secret (delegate to strict check)
    - dryrun/backstage: allow empty key & secret, but if fields missing entirely still flag missing structure
    """
    mode_l = (mode or '').lower()
    strict = validate_user_config(cfg)
    if mode_l in {"dryrun", "backstage"}:
        # Remove empty-value errors for key/secret if structure exists
        filtered: List[str] = []
        for e in strict:
            if e.startswith("Empty required value: exchange.key"):
                continue
            if e.startswith("Empty required value: exchange.secret"):
                continue
            filtered.append(e)
        return filtered
    return strict  # live or unknown keep strict


def validate_bot_config(cfg: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for path in BOT_REQUIRED:
        val = _dig(cfg, path)
        key = '.'.join(path)
        if val is None:
            errors.append(f"Missing required key: {key}")
            continue
        # Structural validations
        if key == 'pair_whitelist':
            if not isinstance(val, list) or not val:
                errors.append("pair_whitelist must be a non-empty list")
        elif key in {'stake_amount'}:
            if not (isinstance(val, (int, float)) or (isinstance(val, str) and val == 'unlimited')):
                errors.append("stake_amount must be number or 'unlimited'")
        elif key == 'dry_run':
            if not isinstance(val, bool):
                errors.append("dry_run must be boolean")
        elif key == 'entry_pricing.price_last_balance':
            if not isinstance(val, (int, float)):
                errors.append("entry_pricing.price_last_balance must be float")
        elif key in {'entry_pricing.price_side', 'exit_pricing.price_side'}:
            if val not in {'ask', 'bid', 'same', 'other'}:
                errors.append(f"{key} invalid value: {val}")
        elif key == 'strategy' and not isinstance(val, str):
            errors.append("strategy must be string class name")
        elif isinstance(val, str) and val.strip() == "":
            errors.append(f"Empty required value: {key}")
    return errors


def validate_bot_config_for_mode(bot_cfg: Dict[str, Any], account_cfg: Dict[str, Any], mode: str | None) -> List[str]:
    """Apply mode-sensitive rules:
    - live: exchange.key & exchange.secret must be non-empty; dry_run must be False
    - dryrun/backstage: dry_run must be True (auto-fix could be considered later)
    - unknown/None: no extra rules
    """
    mode = (mode or '').lower()
    errs: List[str] = []
    # trading_mode specific checks (spot/futures)
    tmode = (bot_cfg or {}).get('trading_mode', 'spot')
    if tmode not in {'spot', 'futures'}:
        errs.append("trading_mode must be 'spot' or 'futures'")
    if tmode == 'spot':
        # Disallow futures-only keys when in spot mode
        if 'liquidation_buffer' in bot_cfg:
            errs.append("spot mode: liquidation_buffer is not applicable")
        if 'margin_mode' in bot_cfg:
            errs.append("spot mode: margin_mode is not applicable")
    elif tmode == 'futures':
        # Optionally validate known futures keys types when present
        if 'liquidation_buffer' in bot_cfg and not isinstance(bot_cfg.get('liquidation_buffer'), (int, float)):
            errs.append("futures mode: liquidation_buffer must be float")
        # margin_mode is exchange-specific, keep as string if provided
        if 'margin_mode' in bot_cfg and not isinstance(bot_cfg.get('margin_mode'), str):
            errs.append("futures mode: margin_mode must be string")
    if mode == 'live':
        exch = (account_cfg or {}).get('exchange', {}) if isinstance(account_cfg, dict) else {}
        if not exch.get('key'):
            errs.append('live.mode: exchange.key required')
        if not exch.get('secret'):
            errs.append('live.mode: exchange.secret required')
        if bot_cfg.get('dry_run') is True:
            errs.append('live.mode: dry_run must be false')
    elif mode in {'dryrun', 'backstage'}:
        if bot_cfg.get('dry_run') is False:
            errs.append(f"{mode}.mode: dry_run must be true")
    return errs


def aggregate_mode_validation(account_cfg: Dict[str, Any], bot_cfg: Dict[str, Any], mode: str | None) -> Dict[str, Any]:
    base_bot_errors = validate_bot_config(bot_cfg)
    user_errors = validate_user_config_for_mode(account_cfg, mode)
    mode_errors = validate_bot_config_for_mode(bot_cfg, account_cfg, mode)
    ok = not (base_bot_errors or user_errors or mode_errors)
    return {
        'user_errors': user_errors,
        'bot_errors': base_bot_errors + mode_errors,
        'ok': ok,
        'mode': mode,
    }

__all__ = [
    'USER_REQUIRED', 'BOT_REQUIRED', 'USER_PLACEHOLDER', 'BOT_PLACEHOLDER',
    'validate_user_config', 'validate_user_config_for_mode', 'validate_bot_config', 'validate_bot_config_for_mode', 'aggregate_mode_validation'
]
