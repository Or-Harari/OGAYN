# Configuration Layering & CRUD API

## Layers (Lowest precedence first)
1. System defaults (hard-coded in `config_service.SYSTEM_DEFAULTS`).
	- Includes: `dry_run`, `trading_mode` (default `spot`), sane `entry_pricing/exit_pricing`, and `initial_state: running`.
2. User-level defaults (`<workspace>/<user>/configs/user/*.json`).
3. User account config (`account.json`) - exchange credentials etc.
4. User meta config (`meta.json`) - strategy meta and active_strategy hint.
5. Bot config (`<workspace>/<user>/bots/<bot>/user_data/configs/bot.json`).
6. Mode file (if present): `live.json` / `dryrun.json` / `backstage.json` merged on top of bot config.
7. Runtime injections (strategy name, pairlists alias, meta duplication into `custom_info` + `strategy_parameters`).

## Required Keys

User-level required (placeholders created on workspace creation):
- `exchange.name` (string)
- `exchange.key` (string, may be empty while `dry_run` is true)
- `exchange.secret` (string, may be empty while `dry_run` is true)

Bot-level required (structural presence + semantic rules; excludes all items listed under "Parameters in the strategy"):
- `pair_whitelist` (non-empty list)
- `stake_currency` (string)
- `stake_amount` (positive float or "unlimited")
- `dry_run` (boolean)
- `unfilledtimeout.entry` / `unfilledtimeout.exit` (ints; `unit` optional)
- `entry_pricing.price_last_balance` (float)
- `entry_pricing.price_side` (one of ask|bid|same|other)
- `exit_pricing.price_side` (one of ask|bid|same|other)
- `strategy` (string class name; defaults to MainStrategy)
 - `trading_mode` (spot|futures) – futures-only keys like `liquidation_buffer`/`margin_mode` are filtered out in spot mode.

Validation occurs at bot start (pre-spawn). All structural requirements must be satisfied; some values may be placeholders during authoring but must be valid when launching (e.g. non-empty `pair_whitelist`).

## API Endpoints (prefix `/config`)
- Meta
	- `GET /config/meta` – fetch merged meta.
	- `PUT /config/meta` – replace meta (body: `{ "meta": { ... } }`).
- User account
	- `GET /config/user` – get full account config (`account.json`).
	- `PATCH /config/user` – partial update account config.
	- `POST /config/user/reset` – restore account config to placeholder scaffold.
	- `GET /config/user/exchange` – get only the exchange section.
	- `PUT /config/user/exchange` – replace exchange section (body matches `ExchangeConfig`).
- Bot config
	- `GET /config/bot/{bot_id}` – get full bot config.
	- `PATCH /config/bot/{bot_id}` – partial update bot config.
	- `POST /config/bot/{bot_id}/reset` – reset bot config (preserves `pair_whitelist` if present).
	- `GET /config/validate/{bot_id}` – run validation and return errors (does not start bot).
	- `GET /config/bot/{bot_id}/trading-controls` – get stake/caps/max-open-trades and related controls.
	- `PUT /config/bot/{bot_id}/trading-controls` – replace trading controls (body matches `BotTradingControls`).
	- `GET /config/bot/{bot_id}/pricing` – get `entry_pricing` and `exit_pricing`.
	- `PUT /config/bot/{bot_id}/pricing` – replace pricing blocks (body matches `BotPricingUpdate`).
	- `PATCH /config/bot/{bot_id}/trading-mode` – set `trading_mode` (spot|futures); removes futures-only keys when switching to spot.

## Validation Helpers
Implemented in `services/config_validation.py`:
- `validate_user_config`, `validate_bot_config` return lists of error strings.
- `validate_user_and_bot` aggregates both.
 - Mode-aware checks: live requires non-empty API key/secret and `dry_run=false`; dryrun/backstage require `dry_run=true`.
 - Trading mode checks: `trading_mode` must be `spot` or `futures`; futures-only keys rejected in spot mode.

## Start Bot Flow
`bot_service.start_bot` now:
1. Runs `validate_user_and_bot`.
2. Raises with aggregated errors if not OK.
3. Composes layered config (`compose_bot_config`).
4. Spawns Freqtrade process.

## Placeholders
Generated via `USER_PLACEHOLDER` and `BOT_PLACEHOLDER` constants ensuring consistent scaffolding, including pricing blocks and `trading_mode`. Strategy-owned keys (timeframe, minimal_roi, stoploss, trailing, unfilledtimeout, etc.) are intentionally not required here and must be defined by the strategy.

## Strategy Parameters
Strategy-specific tunables remain in the strategy and must not be duplicated in bot config. The composer strips them if present.

---
Future enhancements:
- Add optional encryption for API keys at rest.
- Fine-grained validation (exchange-specific requirements, timeframe validation).
- Endpoint for listing effective merged config (post layering) without writing file.
