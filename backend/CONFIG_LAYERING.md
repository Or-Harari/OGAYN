# Configuration Layering & CRUD API

## Layers (Lowest precedence first)
1. System defaults (hard-coded in `config_service.SYSTEM_DEFAULTS`).
2. User-level defaults (`<workspace>/<user>/user/configs/user/*.json`).
3. User account config (`account.json`) - exchange credentials etc.
4. User meta config (`meta.json`) - strategy meta / regime / DCA / paths.
5. Bot config (`<workspace>/<user>/bots/<bot>/user_data/configs/bot.json`).
6. Runtime injections (strategy name, pairlists alias, meta duplication into `custom_info` + `strategy_parameters`).

## Required Keys

User-level required (placeholders created on workspace creation):
- `exchange.name` (string)
- `exchange.key` (string, may be empty while `dry_run` is true)
- `exchange.secret` (string, may be empty while `dry_run` is true)

Bot-level required (structural presence + semantic rules):
- `pair_whitelist` (non-empty list)
- `stake_currency` (string)
- `stake_amount` (positive float or "unlimited")
- `max_open_trades` (int or -1)
- `timeframe` (string)
- `minimal_roi` (non-empty dict)
- `stoploss` (float ratio)
- `dry_run` (boolean)
- `unfilledtimeout.entry` / `unfilledtimeout.exit` (ints; `unit` optional)
- `entry_pricing.price_last_balance` (float)
- `entry_pricing.price_side` (one of ask|bid|same|other)
- `exit_pricing.price_side` (one of ask|bid|same|other)
- `strategy` (string class name; defaults to MainStrategy)

Validation occurs at bot start (pre-spawn). All structural requirements must be satisfied; some values may be placeholders during authoring but must be valid when launching (e.g. non-empty `pair_whitelist`).

## API Endpoints (prefix `/config`)
- `GET /config/meta` – fetch merged meta.
- `PUT /config/meta` – replace meta (body: `{ "meta": { ... } }`).
- `GET /config/user` – get user account config (`account.json`).
- `PATCH /config/user` – partial update account config.
- `POST /config/user/reset` – restore account config to placeholder scaffold.
- `GET /config/bot/{bot_id}` – get bot config.
- `PATCH /config/bot/{bot_id}` – partial update bot config.
- `POST /config/bot/{bot_id}/reset` – reset bot config (preserves existing `pair_whitelist` if present).
- `GET /config/validate/{bot_id}` – run validation and return errors (does not start bot).

## Validation Helpers
Implemented in `services/config_validation.py`:
- `validate_user_config`, `validate_bot_config` return lists of error strings.
- `validate_user_and_bot` aggregates both.

## Start Bot Flow
`bot_service.start_bot` now:
1. Runs `validate_user_and_bot`.
2. Raises with aggregated errors if not OK.
3. Composes layered config (`compose_bot_config`).
4. Spawns Freqtrade process.

## Placeholders
Generated via `USER_PLACEHOLDER` and `BOT_PLACEHOLDER` constants ensuring consistent scaffolding, including newly required numeric and struct keys (`unfilledtimeout`, pricing blocks, etc.).

## Strategy Parameters
Strategy-specific tunables remain in strategy/meta and not duplicated into bot config unless required by runtime.

---
Future enhancements:
- Add optional encryption for API keys at rest.
- Fine-grained validation (exchange-specific requirements, timeframe validation).
- Endpoint for listing effective merged config (post layering) without writing file.
