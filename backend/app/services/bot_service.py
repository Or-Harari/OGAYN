from __future__ import annotations

import zipfile
import os
import subprocess
import json
import time
from pathlib import Path
import sqlite3
from typing import Optional, List, Tuple, Dict
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from ..db.models import BotProcess, User, Bot
from fastapi import HTTPException
from .config_service import compose_bot_config, compose_runtime_config, validate_user_and_bot  # legacy kept
from ..schemas import BacktestStartRequest

def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def _bot_runtime(bot_userdir: Path) -> str:
    """Docker-only runtime (kept for compatibility)."""
    return "docker"


def _docker_container_name(bot: Bot) -> str:
    return f"ft-bot-{bot.id}"


def _docker_is_running(name: str) -> bool:
    try:
        out = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return out.returncode == 0 and out.stdout.strip().lower() == "true"
    except Exception:
        return False


def _docker_remove_container(name: str) -> None:
    try:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _docker_image_ensure(image: str, out_log: Path | None = None) -> None:
    """Ensure docker image exists locally; pull if missing."""
    try:
        probe = subprocess.run(["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode != 0:
            cmd = ["docker", "pull", image]
            if out_log:
                _log_command(out_log, cmd, {"DOCKER": "true"})
            subprocess.run(cmd, check=True)
    except Exception:
        # Best-effort; docker run will error if image truly cannot be pulled
        pass


def _get_freqtrade_image() -> str:
    """Return the freqtrade Docker image to use, honoring env override and pinning default.

    Default pin: freqtrade 2025.8 (aligned with project requirements). Can be overridden via FREQTRADE_IMAGE.
    """
    return os.environ.get("FREQTRADE_IMAGE", "freqtradeorg/freqtrade:2025.8")


# Defaults for Backstage auto data download
DEFAULT_BACKSTAGE_TIMERANGE = os.environ.get("FT_BACKSTAGE_TIMERANGE", "-90d")
DEFAULT_BACKSTAGE_AUTODL_COOLDOWN_HOURS = float(os.environ.get("FT_BACKSTAGE_AUTODL_COOLDOWN_HOURS", "6"))


def _normalize_timerange(value: Optional[str]) -> str:
    """Normalize timerange to Freqtrade-accepted format.

    Accepts:
      - "-90d" or "-90" (days ago to now) -> converts to "YYYYMMDD-"
      - "YYYYMMDD-YYYYMMDD" or "YYYYMMDD-" -> passed through
      - Common ISO-like forms for start/end and converts to "YYYYMMDD-YYYYMMDD" or open-ended
      - Unix seconds (int) for start/end
    """
    try:
        v = (value or "").strip()
        if not v:
            start = datetime.now(timezone.utc) - timedelta(days=90)
            return start.strftime("%Y%m%d") + "-"
        m = re.match(r"^-(\d+)d$", v)
        if m:
            days = int(m.group(1))
            start = datetime.now(timezone.utc) - timedelta(days=days)
            return start.strftime("%Y%m%d") + "-"
        m2 = re.match(r"^-(\d+)$", v)
        if m2:
            days = int(m2.group(1))
            start = datetime.now(timezone.utc) - timedelta(days=days)
            return start.strftime("%Y%m%d") + "-"
        if re.match(r"^\d{8}-(\d{8})?$", v):
            return v
        # Try to parse flexible 'start-end' where tokens may be ISO-like or unix seconds
        def _to_yyyymmdd(tok: str) -> Optional[str]:
            s = (tok or "").strip()
            if not s:
                return None
            # Raw 8 digits
            if re.match(r"^\d{8}$", s):
                return s
            # Unix seconds
            if re.match(r"^\d{10}(?:\d{0,3})$", s):
                try:
                    sec = int(s[:10])
                    dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                    return dt.strftime("%Y%m%d")
                except Exception:
                    pass
            # ISO-like (allow 'T', ' ', and trailing 'Z')
            s2 = s.replace("Z", "").replace("/", "-")
            try:
                # Try full iso first
                dt = None
                try:
                    dt = datetime.fromisoformat(s2)
                except Exception:
                    # Try date-only
                    dt = datetime.fromisoformat(s2.split(" ")[0])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.strftime("%Y%m%d")
            except Exception:
                return None
        # Split start/end by the last '-' to be tolerant of '-' in ISO dates
        if '-' in v:
            idx = v.rfind('-')
            start_raw = v[:idx]
            end_raw = v[idx+1:]
            start_fmt = _to_yyyymmdd(start_raw)
            end_fmt = _to_yyyymmdd(end_raw)
            if start_fmt and end_fmt:
                return f"{start_fmt}-{end_fmt}"
            if start_fmt and (end_raw.strip() == '' or end_fmt is None):
                return f"{start_fmt}-"
        # As a last resort, pass through
        return v
    except Exception:
        start = datetime.now(timezone.utc) - timedelta(days=90)
        return start.strftime("%Y%m%d") + "-"


def _containerize_strategy_path(user_root: Path, bot_userdir: Path, host_path: str | None) -> str | None:
    """Translate a host strategy path to the container mount path.

    - If under bot_userdir -> /freqtrade/user_data/<relative>
    - If under user_root/strategies -> /freqtrade/extra_strategies/<relative>
    Returns None if the path cannot be mapped to known mounts.
    """
    if not host_path:
        return None
    try:
        hp = Path(host_path).resolve()
    except Exception:
        return None
    # bot-local strategies
    try:
        rel = hp.relative_to(bot_userdir)
        # Use posix path for container
        return "/freqtrade/user_data/" + rel.as_posix()
    except Exception:
        pass
    # user workspace extra strategies
    # We mount /freqtrade/extra_strategies to unified <user>/strategies
    extra_base = (user_root / "strategies").resolve()
    try:
        rel = hp.relative_to(extra_base)
        return "/freqtrade/extra_strategies/" + rel.as_posix()
    except Exception:
        pass
    return None


def _log_command(out_log: Path, cmd: list[str], env_additions: dict[str, str]) -> None:
    line = f"\n==== BOT START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\nCMD: {' '.join(cmd)}\nENV_ADD: {json.dumps(env_additions)}\n"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    with out_log.open("ab") as f:
        f.write(line.encode("utf-8", errors="ignore"))


def _sanitize_pair_tokens(pair: str) -> List[str]:
    """Return common filename token variations for a trading pair.

    - Handles futures contract suffix ":QUOTE" (e.g., "BTC/USDT:USDT") by generating tokens both
      with the full quote and with the stripped quote ("USDT").
    - Examples for BTC/USDT -> ["BTC_USDT", "BTC-USDT", "BTCUSDT", "USDT_BTC", "USDT-BTC"].
    This is used to heuristically locate downloaded candle files.
    """
    try:
        p = (pair or "").replace(" ", "").strip()
        if not p:
            return []
        if "/" in p:
            base, quote = p.split("/", 1)
        elif "-" in p:
            base, quote = p.split("-", 1)
        elif "_" in p:
            base, quote = p.split("_", 1)
        else:
            # Guess split for concatenated like BTCUSDT -> try last 3-4 letters as quote
            base, quote = p[:-4], p[-4:]
        # If futures, quote may be like 'USDT:USDT' - generate with and without suffix
        quote_main = quote.split(":", 1)[0] if ":" in quote else quote
        quotes = [q for q in [quote, quote_main] if q]
        tokens: List[str] = []
        for q in quotes:
            tokens.extend([
                f"{base}_{q}", f"{base}-{q}", f"{base}{q}",
                f"{q}_{base}", f"{q}-{base}", f"{q}{base}",
            ])
        # Unique preserving order
        seen = set()
        out: List[str] = []
        for t in tokens:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out
    except Exception:
        return []


def _has_data_for_pair_tf(data_root: Path, exchange: str, pair: str, timeframe: str, candle_type: str | None = None) -> bool:
    """Check if candle data exists locally for a specific pair/timeframe.

    Be stricter to avoid false-positives (e.g., matching only the quote like 'USDT').
    Requires that BOTH base and quote symbols occur in the filename alongside the timeframe.
    """
    try:
        ex_dir = data_root / exchange
        if not ex_dir.exists():
            return False
        tf = (timeframe or "").strip().lower()
        if not tf:
            return False
        # Extract base/quote (ignore futures suffix after ':')
        base = quote = None
        try:
            ps = str(pair).strip()
            if ":" in ps:
                ps, _ = ps.split(":", 1)
            if "/" in ps:
                base, quote = ps.split("/", 1)
            elif "-" in ps:
                base, quote = ps.split("-", 1)
            elif "_" in ps:
                base, quote = ps.split("_", 1)
            else:
                # Heuristic fallback (last 4 are quote)
                base, quote = ps[:-4], ps[-4:]
        except Exception:
            base = quote = None
        if not base or not quote:
            return False
        b = base.lower()
        q = quote.lower()
        # Walk a limited depth to avoid heavy IO (up to 3 levels below exchange)
        for root, dirs, files in os.walk(ex_dir):
            try:
                if str(root).count(os.sep) - str(ex_dir).count(os.sep) > 3:
                    dirs[:] = []
                    continue
            except Exception:
                pass
            for fname in files:
                lower = fname.lower()
                full_path_lower = str(Path(root) / fname).lower()
                if tf not in lower:
                    continue
                # Filter by candle type if provided: futures files usually live under '/futures' dir or include '-futures' in name
                ct = (candle_type or "").strip().lower()
                if ct == "futures":
                    if ("/futures" not in full_path_lower.replace("\\", "/")) and ("-futures" not in lower):
                        continue
                elif ct in ("spot", ""):
                    # Exclude futures-specific files when checking for spot data
                    if ("/futures" in full_path_lower.replace("\\", "/")) or ("-futures" in lower):
                        continue
                # Require both base and quote to be present in the filename
                if b in lower and q in lower:
                    return True
                # Also accept compact concatenations like BTCUSDT
                if (b + q) in lower or (b + "_" + q) in lower or (b + "-" + q) in lower:
                    return True
        return False
    except Exception:
        return False


def _normalize_pairs_for_market(pairs: List[str], market_type: str, exchange: str) -> List[str]:
    """Normalize pair symbols for specific markets/exchanges.

    - Binance Futures requires a contract suffix on pairs, e.g. "BTC/USDT:USDT".
      If market_type=="futures" and exchange=="binance", append ":<QUOTE>" when missing.
    - Leaves pairs unchanged for other exchanges/markets.
    """
    try:
        mt = (market_type or "").lower().strip()
        ex = (exchange or "").lower().strip()
        if mt != "futures" or ex != "binance":
            return pairs
        out: List[str] = []
        for p in pairs:
            try:
                if not isinstance(p, str):
                    out.append(p)
                    continue
                ps = p.strip()
                if ":" in ps:
                    # Already has a contract suffix
                    out.append(ps)
                    continue
                if "/" in ps:
                    base, quote = ps.split("/", 1)
                elif "-" in ps:
                    base, quote = ps.split("-", 1)
                elif "_" in ps:
                    base, quote = ps.split("_", 1)
                else:
                    # Fallback: assume last 4 chars are quote (e.g., BTCUSDT)
                    base, quote = ps[:-4], ps[-4:]
                quote = (quote or "USDT").upper()
                out.append(f"{base}/{quote}:{quote}")
            except Exception:
                out.append(p)
        return out
    except Exception:
        return pairs


def _download_data_sync(user_root: Path, bot_userdir: Path, exchange: str, pairs: List[str], timeframes: List[str], timerange: str, candle_type: str | None = None, prepend: bool = False) -> None:
    """Run 'freqtrade download-data' in a blocking way inside docker to ensure data exists before backtest.

    Logs will be written to user_data/logs/download-data.*.log.
    """
    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "download-data.out.log"
    err_log = logs_dir / "download-data.err.log"

    extra_strategy_dir = user_root / "strategies"
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    docker_py_path = "/freqtrade/user_data:/repo"
    volumes = [f"{str(bot_userdir)}:/freqtrade/user_data", f"{str(repo_root)}:/repo"]
    if extra_strategy_dir and extra_strategy_dir.exists():
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/extra_strategies")
        docker_py_path = f"{docker_py_path}:/freqtrade/extra_strategies"
    image = _get_freqtrade_image()
    _docker_image_ensure(image, out_log)
    # Normalize timerange like "-90d" to "YYYYMMDD-"
    try:
        timerange = _normalize_timerange(timerange)
    except Exception:
        pass
    base_cmd = ["docker", "run"]
    for v in volumes:
        base_cmd += ["-v", v]
    base_cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
    # Force headless matplotlib backend to avoid libtk errors inside slim containers
    base_cmd += ["-e", "MPLBACKEND=Agg"]
    # Set container timezone for consistent logs
    try:
        tz = os.environ.get("FT_CONTAINER_TZ", os.environ.get("TZ", "Asia/Jerusalem"))
    except Exception:
        tz = "Asia/Jerusalem"
    base_cmd += ["-e", f"TZ={tz}"]
    base_cmd += [
        image,
        "download-data",
        "--exchange", exchange,
        "--timerange", timerange,
        "--userdir", "/freqtrade/user_data",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
    ]
    if prepend:
        base_cmd += ["--prepend"]
    # Prepare 2 variants: with and without '--candle-type futures' for compatibility across FT versions
    with_ct = list(base_cmd)
    without_ct = list(base_cmd)
    if (candle_type or "").lower() == "futures":
        # Normalize pairs for Binance Futures contract notation
        pairs = _normalize_pairs_for_market(pairs, "futures", exchange)
        with_ct += ["--candle-type", "futures"]
    # Pass timeframes and pairs as single flags with all values to avoid argparse overriding earlier ones
    if timeframes:
        with_ct += ["-t", *timeframes]
        without_ct += ["-t", *timeframes]
    if pairs:
        with_ct += ["-p", *pairs]
        without_ct += ["-p", *pairs]

    env = os.environ.copy()
    # Try with '--candle-type futures' first when in futures mode; on unrecognized-arg error, retry without the flag
    attempts = [with_ct] if (candle_type or "").lower() == "futures" else [without_ct]
    if (candle_type or "").lower() == "futures":
        attempts.append(without_ct)
    last_err: str | None = None
    for idx, cmd in enumerate(attempts):
        _log_command(out_log, cmd, {"PYTHONPATH": docker_py_path, "AUTO": "download-before-backtest"})
        with out_log.open("ab") as out, err_log.open("ab") as err:
            try:
                subprocess.run(
                    cmd,
                    stdout=out,
                    stderr=err,
                    cwd=str(bot_userdir),
                    shell=False,
                    env=env,
                    check=True,
                )
                last_err = None
                break
            except Exception as e:
                try:
                    data = err_log.read_bytes()[-4096:]
                    tail = data.decode("utf-8", errors="ignore").strip().splitlines()
                    last_err = tail[-1] if tail else str(e)
                except Exception:
                    last_err = str(e)
                # If this was the first attempt with '--candle-type' and error indicates unrecognized argument, continue to retry
                if idx == 0 and (candle_type or "").lower() == "futures":
                    low = (last_err or "").lower()
                    if "unrecognized arguments" in low and "candle-type" in low:
                        continue
                # Otherwise fail
                break
    if last_err:
        # Fallback: try per-pair downloads to skip problematic pairs (e.g., virtual/test pairs)
        successes = 0
        errors: list[str] = []
        for p in (pairs or []):
            for idx, template in enumerate(attempts):
                # Build per-pair command by replacing any existing -p list with single pair
                cmd = [c for c in template if c != "-p" and not (isinstance(c, str) and c in pairs)]
                # Reconstruct command cleanly
                cmd = list(template)
                # Remove any existing pairs specification
                try:
                    if "-p" in cmd:
                        i = cmd.index("-p")
                        # Remove -p and following N entries until next flag or end
                        j = i + 1
                        while j < len(cmd) and not str(cmd[j]).startswith("-"):
                            j += 1
                        del cmd[i:j]
                except Exception:
                    pass
                cmd += ["-p", p]
                _log_command(out_log, cmd, {"PYTHONPATH": docker_py_path, "AUTO": "download-before-backtest:per-pair"})
                with out_log.open("ab") as out, err_log.open("ab") as err:
                    try:
                        subprocess.run(
                            cmd,
                            stdout=out,
                            stderr=err,
                            cwd=str(bot_userdir),
                            shell=False,
                            env=env,
                            check=True,
                        )
                        successes += 1
                        break
                    except Exception as e:
                        # try next attempt variant (with/without --candle-type)
                        if idx == len(attempts) - 1:
                            # record final error for this pair
                            try:
                                data = err_log.read_bytes()[-4096:]
                                tail = data.decode("utf-8", errors="ignore").strip().splitlines()
                                errors.append(f"{p}: {tail[-1] if tail else str(e)}")
                            except Exception:
                                errors.append(f"{p}: {str(e)}")
                        continue
        if successes == 0:
            raise HTTPException(status_code=502, detail={"message": "download-data failed", "error": last_err, "per_pair_errors": errors})


# ----- Helpers for backtest/running container discovery and log tailing -----
def _list_backtest_containers(bot_id: int) -> List[str]:
    """Return names of backtest containers for this bot (any state), newest first.

    Containers are named ft-bt-<bot_id>-<timestamp> by start_backtest().
    """
    try:
        # List all containers matching name substring; format with names only
        out = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=ft-bt-{bot_id}-", "--format", "{{.Names}}"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore"
        )
        if out.returncode != 0:
            return []
        names = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if not names:
            return []
        # Sort by Created time desc
        def created_ts(nm: str) -> float:
            try:
                c = subprocess.run(["docker", "inspect", "-f", "{{.Created}}", nm], capture_output=True, text=True, encoding="utf-8", errors="ignore")
                s = c.stdout.strip()
                # RFC3339-like -> parse to epoch; fallback to 0 on error
                from datetime import datetime
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
                except Exception:
                    return 0.0
            except Exception:
                return 0.0
        names.sort(key=created_ts, reverse=True)
        return names
    except Exception:
        return []


def _inspect_container(name: str) -> Dict[str, Optional[str]]:
    """Return selected docker inspect fields for a container name."""
    try:
        fmt = "{{.State.Running}}|{{.State.ExitCode}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.Name}}"
        out = subprocess.run(["docker", "inspect", "-f", fmt, name], capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if out.returncode != 0:
            return {}
        parts = out.stdout.strip().split("|")
        running = parts[0] if len(parts) > 0 else None
        exit_code = parts[1] if len(parts) > 1 else None
        started = parts[2] if len(parts) > 2 else None
        finished = parts[3] if len(parts) > 3 else None
        cname = parts[4] if len(parts) > 4 else None
        return {
            "running": running,
            "exit_code": exit_code,
            "started_at": started,
            "finished_at": finished,
            "name": cname.lstrip("/") if cname else name,
        }
    except Exception:
        return {}


## Backstage analysis (removed per simplified design)


def _docker_logs_tail(name: str, tail: int = 1000) -> List[str]:
    try:
        t = max(1, min(int(tail), 10000))
    except Exception:
        t = 1000
    try:
        out = subprocess.run(["docker", "logs", "--tail", str(t), name], capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if out.returncode != 0:
            return []
        # Normalize newlines and split
        return out.stdout.splitlines()
    except Exception:
        return []


def _tail_file_lines(path: Path, tail: int = 1000) -> List[str]:
    """Tail last N lines from a text file efficiently. Returns [] if not readable."""
    try:
        if not path.exists() or not path.is_file():
            return []
        t = max(1, min(int(tail), 20000))
        # heuristic: read chunks from end until we collected enough newlines
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = 4096
            data = b""
            lines_found = 0
            pos = size
            while pos > 0 and lines_found <= t:
                step = chunk if pos >= chunk else pos
                f.seek(pos - step)
                buf = f.read(step)
                data = buf + data
                lines_found = data.count(b"\n")
                pos -= step
            text = data.decode('utf-8', errors='ignore')
            lines = text.splitlines()
            return lines[-t:]
    except Exception:
        return []


def start_bot(db: Session, user: User, bot: Bot, config_path: Optional[str] = None) -> BotProcess:
    """Start a bot process using per-bot workspace and layered config.

    Args:
        user: owning user (for user root path)
        bot: bot DB record (bot.userdir points to bot user_data root)
        config_path: optional explicit config (normally ignored; we compose fresh)
    """
    user_root = Path(user.workspace_root).resolve()
    # Docker-only: enforce single-instance by container state
    existing = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    bot_userdir = Path(bot.userdir).resolve()
    # Auto-sync dry_run flag to mode before validation (in-memory adjustment only; not persisted here)
    mode = getattr(bot, "mode", None)
    if mode:
        mode_l = mode.lower()
        # Load bot config raw to adjust dry_run if inconsistent
        bot_cfg_path = Path(bot_userdir) / "configs" / "bot.json"
        try:
            if bot_cfg_path.exists():
                raw = json.loads(bot_cfg_path.read_text(encoding="utf-8")) or {}
                desired = (mode_l in {"dryrun", "backstage"})
                if mode_l == "live":
                    desired = False
                if raw.get("dry_run") != desired:
                    raw["dry_run"] = desired
                    bot_cfg_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass
    # Pre-validation (mode-aware, with relaxed credentials for non-live)
    validation = validate_user_and_bot(str(user_root), str(bot_userdir), mode=mode)
    if not validation.get("ok"):
        detail = {
            "message": "Configuration validation failed",
            "mode": validation.get("mode"),
            "user_errors": validation.get("user_errors", []),
            "bot_errors": validation.get("bot_errors", []),
        }
        raise HTTPException(status_code=422, detail=detail)

    # Compose layered config inside bot workspace
    # Decode active strategy spec if stored
    active_strategy_spec = None
    if getattr(bot, "active_strategy", None):
        try:
            active_strategy_spec = json.loads(bot.active_strategy)
        except Exception:
            active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        # Fallback to deprecated runtime config (legacy path) if something unexpected happens
        cfg_path = compose_runtime_config(str(bot_userdir))

    # Backstage no longer auto-triggers download-data; keep start minimal per simplified design

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "bot.out.log"
    err_log = logs_dir / "bot.err.log"

    # Docker runtime (only)
    if not _docker_available():
        raise HTTPException(status_code=503, detail="Docker is not available on this host.")
    name = _docker_container_name(bot)
    if _docker_is_running(name):
        raise HTTPException(status_code=409, detail={"message": "Bot container is already running", "container": name})
    # Ensure required runtime fields prior to running (single source of truth)
    # NOTE: Timeframe is now optional at this pre-start phase. If it's only
    #       defined inside the Strategy class (and absent in config), we allow
    #       the container to attempt start and let Freqtrade emit a clear error.
    #       We only hard-require 'strategy' and trading pairs here.
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_json = json.load(f) or {}
    except Exception:
        cfg_json = {}
    missing_fields = []
    strategy_val = cfg_json.get("strategy")
    if not (isinstance(strategy_val, str) and strategy_val.strip()) or strategy_val.strip() == "__SET_YOUR_STRATEGY__":
        missing_fields.append("strategy")
    pairs_list = None
    try:
        if isinstance(cfg_json.get("pairs"), list):
            pairs_list = cfg_json.get("pairs")
        elif isinstance(cfg_json.get("pair_whitelist"), list):
            pairs_list = cfg_json.get("pair_whitelist")
    except Exception:
        pairs_list = None
    if not (isinstance(pairs_list, list) and len(pairs_list) > 0):
        missing_fields.append("pairs")
    if missing_fields:
        raise HTTPException(status_code=422, detail={"message": "Missing required fields", "missing": missing_fields})
    # Publish API port and resolve strategy path mapping into container
    try:
        api = cfg_json.get("api_server", {}) if 'cfg_json' in locals() else {}
        host_port = int(api.get("listen_port", 8080) if api else 8080)
    except Exception:
        host_port = 8080
    # Remap strategy_path to container path if present
    container_spath = None
    try:
        container_spath = _containerize_strategy_path(user_root, bot_userdir, cfg_json.get("strategy_path") if cfg_json else None)
    except Exception:
        container_spath = None
    # If we have a valid container strategy path, update the generated config so Freqtrade doesn't see Windows paths
    try:
        if container_spath and cfg_json is not None:
            cfg_json["strategy_path"] = container_spath
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_json, f, indent=2)
    except Exception:
        pass
    # Strategy extras mount - unified user strategies directory
    extra_strategy_dir = Path(user_root) / "strategies"
    # Mount repo root to make `backend.app.*` imports available inside the container
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    docker_py_path = "/freqtrade/user_data:/repo"
    volumes: list[str] = [f"{str(bot_userdir)}:/freqtrade/user_data", f"{str(repo_root)}:/repo"]
    if extra_strategy_dir and extra_strategy_dir.exists():
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/extra_strategies")
        docker_py_path = f"{docker_py_path}:/freqtrade/extra_strategies"
    image = _get_freqtrade_image()
    _docker_image_ensure(image, out_log)
    cmd = [
        "docker", "run", "-d",
        "--name", name,
        # Map host listen_port -> container listen_port (matches Freqtrade config)
        "-p", f"127.0.0.1:{host_port}:{host_port}",
    ]
    for v in volumes:
        cmd += ["-v", v]
    cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
    # Ensure headless matplotlib backend (prevents libtk8.6.so import errors)
    cmd += ["-e", "MPLBACKEND=Agg"]
    # Set container timezone for consistent logs
    try:
        tz = os.environ.get("FT_CONTAINER_TZ", os.environ.get("TZ", "Etc/UTC"))
    except Exception:
        tz = "Etc/UTC"
    cmd += ["-e", f"TZ={tz}"]
    cmd += [
        image,
        "trade",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
        "--userdir", "/freqtrade/user_data",
    ]
    if container_spath:
        cmd += ["--strategy-path", container_spath]
    env = os.environ.copy()
    _log_command(out_log, cmd, {"DOCKER": "true"})
    # Run docker command synchronously to detect immediate failures (e.g., daemon down)
    try:
        with out_log.open("ab") as out, err_log.open("ab") as err:
            subprocess.run(
                cmd,
                stdout=out,
                stderr=err,
                cwd=str(bot_userdir),
                shell=False,
                env=env,
                check=True,
            )
    except Exception as e:
        # Mark process as error and include a brief error snippet for diagnostics
        rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
        if not rec:
            rec = BotProcess(bot_id=bot.id)
            db.add(rec)
        rec.pid = None
        rec.status = "error"
        rec.config_path = str(cfg_path)
        rec.exit_code = 1
        try:
            with err_log.open("rb") as ef:
                data = ef.read()[-2048:]
            snippet = data.decode("utf-8", errors="ignore").strip()
            rec.last_error = snippet.splitlines()[-1] if snippet else str(e)
        except Exception:
            rec.last_error = str(e)
        db.commit()
        db.refresh(rec)
        # Surface the failure to caller
        raise HTTPException(status_code=502, detail={"message": "Bot could not start", "error": rec.last_error})

    # Verify container actually running; otherwise flag as error
    # Verify container actually running; otherwise flag as error
    if not _docker_is_running(name):
        rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
        if not rec:
            rec = BotProcess(bot_id=bot.id)
            db.add(rec)
        rec.pid = None
        rec.status = "error"
        rec.config_path = str(cfg_path)
        rec.exit_code = 1
        try:
            with err_log.open("rb") as ef:
                data = ef.read()[-2048:]
            snippet = data.decode("utf-8", errors="ignore").strip()
            rec.last_error = snippet.splitlines()[-1] if snippet else "Container not running after start"
        except Exception:
            rec.last_error = "Container not running after start"
        db.commit()
        db.refresh(rec)
        raise HTTPException(status_code=502, detail={"message": "Bot could not start", "error": rec.last_error})

    # Persist / replace existing BotProcess for this bot
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec:
        rec = BotProcess(bot_id=bot.id)
        db.add(rec)
    rec.pid = None
    rec.status = "running"
    rec.config_path = str(cfg_path)
    rec.exit_code = None
    rec.last_error = None
    db.commit()
    db.refresh(rec)
    return rec


# start_api_only removed per revised design


def stop_bot(db: Session, bot: Bot) -> BotProcess:
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    name = _docker_container_name(bot)
    if _docker_is_running(name):
        _docker_remove_container(name)
    if not rec:
        rec = BotProcess(bot_id=bot.id)
        db.add(rec)
    rec.status = "stopped"
    rec.pid = None
    db.commit()
    db.refresh(rec)
    return rec


def bot_status(db: Session, bot: Bot):
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    name = _docker_container_name(bot)
    running = _docker_is_running(name)
    # Report running only if the container is actually running. Otherwise prefer 'stopped';
    # keep 'backtesting' or 'error' statuses to aid diagnostics.
    if running:
        status = "running"
    else:
        status = "stopped"
        if rec and rec.status in {"backtesting", "error"}:
            status = rec.status
    return {
        "status": status,
        "pid": None,
        "config": rec.config_path if rec else None,
        "exit_code": rec.exit_code if rec else None,
        "last_error": rec.last_error if rec else None,
        "container": name,
    }


def start_backtest(db: Session, user: User, bot: Bot, params: BacktestStartRequest) -> BotProcess:
    """Start a backtest process for the given bot using its composed config.

    This uses freqtrade backtesting mode and writes outputs to the bot's user_data.
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()
    # Validate config environment (mode does not matter for backtest, but we'll keep relaxed creds)
    validation = validate_user_and_bot(str(user_root), str(bot_userdir), mode=getattr(bot, "mode", None))
    if not validation.get("ok"):
        detail = {
            "message": "Configuration validation failed",
            "mode": validation.get("mode"),
            "user_errors": validation.get("user_errors", []),
            "bot_errors": validation.get("bot_errors", []),
        }
        raise HTTPException(status_code=422, detail=detail)

    # Compose config (honors active_strategy)
    try:
        active_strategy_spec = None
        if getattr(bot, "active_strategy", None):
            active_strategy_spec = json.loads(bot.active_strategy)
    except Exception:
        active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        cfg_path = compose_runtime_config(str(bot_userdir))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "backtest.out.log"
    err_log = logs_dir / "backtest.err.log"

    # Docker runtime only
    if not _docker_available():
        raise HTTPException(status_code=503, detail="Docker is not available on this host.")
    # no host branch

    # Read composed config to determine strategy, exchange, pairs and timeframes
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_json = json.load(f) or {}
    except Exception:
        cfg_json = {}
    # Determine effective strategy (params.strategy > cfg.strategy > meta.active_strategy)
    strategy_name: Optional[str] = None
    if isinstance(params.strategy, str) and params.strategy:
        strategy_name = params.strategy
    else:
        try:
            strategy_name = cfg_json.get("strategy")
        except Exception:
            strategy_name = None
        if strategy_name in {None, "", "__SET_YOUR_STRATEGY__"}:
            try:
                if getattr(bot, "active_strategy", None):
                    act = json.loads(bot.active_strategy)
                    strategy_name = (act.get("clazz") or act.get("name")) if isinstance(act, dict) else None
                    if isinstance(strategy_name, str) and strategy_name.lower().endswith(".py"):
                        strategy_name = strategy_name[:-3]
            except Exception:
                pass
    if not strategy_name or strategy_name == "__SET_YOUR_STRATEGY__":
        raise HTTPException(status_code=422, detail="No strategy specified. Set an active strategy for this bot or pass 'strategy' in the backtest request.")

    # Gather exchange, pairs, and timeframes for data checks
    try:
        exchange_name = ((cfg_json.get("exchange") or {}).get("name") or "binance")
    except Exception:
        exchange_name = "binance"
    # Prefer pairs key; else pair_whitelist
    pairs: List[str] = []
    try:
        if isinstance(cfg_json.get("pairs"), list):
            pairs = cfg_json.get("pairs") or []
        elif isinstance(cfg_json.get("pair_whitelist"), list):
            pairs = cfg_json.get("pair_whitelist") or []
    except Exception:
        pairs = []
    # Optional overrides from request
    try:
        override_pairs: List[str] = []
        if getattr(params, "pairs", None):
            if isinstance(params.pairs, list):
                override_pairs = [str(p).strip().upper() for p in params.pairs if str(p).strip()]
        elif getattr(params, "pair", None):
            override_pairs = [str(params.pair).strip().upper()]
    except Exception:
        override_pairs = []
    if override_pairs:
        pairs = override_pairs
    # Discover timeframes used by the strategy (timeframe + informative_timeframe if any)
    strat_tfs = _import_strategy_timeframes(str(cfg_path))
    try:
        override_tfs: List[str] = []
        if getattr(params, "timeframes", None):
            if isinstance(params.timeframes, list):
                override_tfs = [str(t).strip() for t in params.timeframes if str(t).strip()]
        elif getattr(params, "timeframe", None):
            override_tfs = [str(params.timeframe).strip()]
    except Exception:
        override_tfs = []
    # Build robust effective timeframes for data download:
    # - Always include override timeframe if present
    # - Also include strategy timeframe(s) to support strategies using different primary TF than backtest request
    # - If nothing is found, default to ["5m"] to avoid 1m fallback in freqtrade
    tfs_effective: List[str] = []
    seen_tf: set[str] = set()
    for lst in (override_tfs, strat_tfs):
        for tf in (lst or []):
            s = (tf or "").strip()
            if s and s not in seen_tf:
                seen_tf.add(s)
                tfs_effective.append(s)
    if not tfs_effective:
        tfs_effective = ["5m"]
    if not pairs:
        # If still no pairs after overrides, surface as a validation error early
        raise HTTPException(status_code=422, detail="No pairs configured. Provide 'pair(s)' in request or set pair_whitelist/pairs in config before backtesting.")

    # Ensure data exists for the requested backtest range
    try:
        data_root = bot_userdir / "data"
        # Debug log setup (append-only) for decision tracing
        debug_log = logs_dir / "backtest.debug.log"
        def _dbg(msg: str) -> None:
            try:
                debug_log.parent.mkdir(parents=True, exist_ok=True)
                with debug_log.open("a", encoding="utf-8") as df:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    df.write(f"[{ts}] {msg}\n")
            except Exception:
                pass
        _dbg(f"strategy={strategy_name} exchange={exchange_name} pairs={pairs} override_tfs={override_tfs} strat_tfs={strat_tfs} tfs_effective={tfs_effective} timerange_param={params.timerange!r}")
        # Detect if ANY existing data is present to decide on '--prepend' usage
        has_existing_any = False
        candle_type = "futures" if str((cfg_json.get("trading_mode") or "spot")).lower() == "futures" else "spot"
        try:
            for p in pairs:
                for tf in (tfs_effective or []):
                    if _has_data_for_pair_tf(data_root, exchange_name, p, tf, candle_type=candle_type):
                        has_existing_any = True
                        break
                if has_existing_any:
                    break
        except Exception:
            has_existing_any = False
        _dbg(f"has_existing_any={has_existing_any}")
        # If an explicit timerange was requested, force a blocking download for that range to guarantee coverage
        if params.timerange and isinstance(params.timerange, str) and params.timerange.strip():
            dl_timerange = _normalize_timerange(params.timerange)
            candle_type = candle_type
            _dbg(f"Forced download due to explicit timerange dl_timerange={dl_timerange} candle_type={candle_type} prepend={has_existing_any}")
            # Use '--prepend' only when we already have some data locally; otherwise download forward normally
            _download_data_sync(Path(user_root), bot_userdir, exchange_name, pairs, tfs_effective, dl_timerange, candle_type=candle_type, prepend=has_existing_any)
        else:
            # Otherwise, run a presence check and download a sensible default window when missing
            need_download = False
            for p in pairs:
                for tf in tfs_effective:
                    if not _has_data_for_pair_tf(data_root, exchange_name, p, tf, candle_type=candle_type):
                        need_download = True
                        _dbg(f"Missing data detected pair={p} timeframe={tf}")
                        break
                if need_download:
                    break
            _dbg(f"need_download={need_download}")
            if need_download:
                dl_timerange = DEFAULT_BACKSTAGE_TIMERANGE
                candle_type = candle_type
                _dbg(f"Initiating download dl_timerange={dl_timerange} candle_type={candle_type} prepend={has_existing_any}")
                _download_data_sync(Path(user_root), bot_userdir, exchange_name, pairs, tfs_effective, dl_timerange, candle_type=candle_type, prepend=has_existing_any)
            else:
                _dbg("Skip download (all pairs/timeframes appear present)")
    except HTTPException:
        # Bubble up HTTP errors
        raise
    except Exception:
        _dbg("Download decision block raised unexpected exception; proceeding without blocking download")
        # Best-effort; proceed to backtest which may still succeed if partial data exists
        pass

    # Build docker command for backtesting
    name = f"ft-bt-{bot.id}-{int(time.time())}"
    extra_strategy_dir = Path(user_root) / "strategies"
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    docker_py_path = "/freqtrade/user_data:/repo"
    volumes = [f"{str(bot_userdir)}:/freqtrade/user_data", f"{str(repo_root)}:/repo"]
    if extra_strategy_dir and extra_strategy_dir.exists():
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/extra_strategies")
        docker_py_path = f"{docker_py_path}:/freqtrade/extra_strategies"
    image = _get_freqtrade_image()
    _docker_image_ensure(image, out_log)
    cmd = ["docker", "run", "-d", "--name", name]
    for v in volumes:
        cmd += ["-v", v]
    cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
    # Ensure headless matplotlib backend during backtests
    cmd += ["-e", "MPLBACKEND=Agg"]
    # Set container timezone for consistent logs
    try:
        tz = os.environ.get("FT_CONTAINER_TZ", os.environ.get("TZ", "Asia/Jerusalem"))
    except Exception:
        tz = "Asia/Jerusalem"
    cmd += ["-e", f"TZ={tz}"]
    cmd += [
        image,
        "backtesting",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
        "--userdir", "/freqtrade/user_data",
    ]
    # Ensure backtesting respects trading_mode via config/pair format (do not pass '--candle-type')
    try:
        tmode = str((cfg_json.get("trading_mode") or "spot")).lower()
    except Exception:
        tmode = "spot"
    # Remap strategy_path for backtesting as well (if strategy_path exists in config)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            _cfgjson = json.load(f)
        _spath = _containerize_strategy_path(user_root, bot_userdir, _cfgjson.get("strategy_path"))
        if _spath:
            cmd += ["--strategy-path", _spath]
    except Exception:
        pass
    # Always pass the resolved strategy explicitly to avoid placeholder issues
    if strategy_name:
        cmd += ["--strategy", strategy_name]
    # Normalize timerange if provided
    if params.timerange:
        try:
            norm = _normalize_timerange(params.timerange)
        except Exception:
            norm = params.timerange
        cmd += ["--timerange", norm]
    # Apply timeframe override (only primary timeframe is supported by 'backtesting')
    if override_tfs:
        primary_tf = override_tfs[0]
        if isinstance(primary_tf, str) and primary_tf:
            cmd += ["--timeframe", primary_tf]
    # Apply pair overrides (normalize to futures contract notation when needed)
    if override_pairs:
        bt_pairs = list(override_pairs)
        if tmode == "futures":
            try:
                bt_pairs = _normalize_pairs_for_market(bt_pairs, "futures", exchange_name)
            except Exception:
                bt_pairs = list(override_pairs)
        if bt_pairs:
            cmd += ["-p", *bt_pairs]
    if params.export != "none":
        cmd += ["--export", params.export]
        if params.export_filename:
            cmd += ["--export-filename", params.export_filename]

    # Env setup similar to start_bot
    env = os.environ.copy()
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    py_path_parts = [str(user_root), str(repo_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(py_path_parts)
    _log_command(out_log, cmd, {"PYTHONPATH": env["PYTHONPATH"]})

    with out_log.open("ab") as out, err_log.open("ab") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )

    # Track as a BotProcess record tagged via status 'backtesting'
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec:
        rec = BotProcess(bot_id=bot.id)
        db.add(rec)
    rec.pid = proc.pid
    rec.status = "backtesting"
    rec.config_path = str(cfg_path)
    rec.exit_code = None
    rec.last_error = None
    db.commit()
    db.refresh(rec)

    time.sleep(float(os.environ.get("FT_BOT_EARLY_EXIT_WAIT", "0.5")))
    if proc.poll() is not None:
        rec.exit_code = proc.returncode
        rec.status = "error" if proc.returncode else "stopped"
        try:
            with err_log.open("rb") as ef:
                data = ef.read()[-2048:]
            snippet = data.decode("utf-8", errors="ignore")
            rec.last_error = snippet.strip().splitlines()[-10:][-1] if snippet else "Exited immediately"
        except Exception:
            rec.last_error = "Exited immediately (log unreadable)"
        db.commit()
        db.refresh(rec)
    return rec


def get_backtest_results(bot: Bot, limit_trades: int = 200) -> dict:
    """Load latest backtest export (trades) and compute a simple summary."""
    import json as _json
    
    def _extract_trades(payload) -> list:
        """
        Return a list of trades from various possible backtest result shapes:
        - [ {trade}, ... ]
        - { "trades": [...] }
        - { "strategy": { "<name>": { "trades": [...] } } }
        """
        # Case 1: payload is already a list of trades
        if isinstance(payload, list):
            return payload

        if not isinstance(payload, dict):
            return []

        # Case 2: top-level "trades"
        if isinstance(payload.get("trades"), list):
            return payload["trades"]

        # Case 3: nested under "strategy" -> "<strategy_name>" -> "trades"
        strategy_block = payload.get("strategy")
        if isinstance(strategy_block, dict):
            for strat_obj in strategy_block.values():
                if isinstance(strat_obj, dict) and isinstance(strat_obj.get("trades"), list):
                    return strat_obj["trades"]

        return []

    bot_userdir = Path(bot.userdir).resolve()
    results_dir = bot_userdir / "backtest_results"
    if not results_dir.exists():
        return {"trades": [], "summary": {}}

    # Find the latest *.json descriptor (e.g., latest.json)
    files = sorted(
        results_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    if not files:
        return {"trades": [], "summary": {}}

    latest = files[0]

    # Read descriptor and open the referenced ZIP -> JSON (same basename)
    try:
        latest_payload = _json.loads(latest.read_text(encoding="utf-8"))
        zip_filename = latest_payload.get("latest_backtest")
        if not zip_filename:
            raise KeyError("Key 'latest_backtest' missing in latest descriptor JSON")
    except Exception as e:
        print(f"Failed to read latest descriptor {latest}: {e}")
        return {"trades": [], "summary": {}}

    zip_path = (latest.parent / zip_filename).resolve()
    if not zip_path.exists():
        print(f"Backtest ZIP not found: {zip_path}")
        return {"trades": [], "summary": {}}

    inner_json_name = Path(zip_filename).stem + ".json"

    # Load JSON from inside the ZIP (support subfolders)
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            target_name = inner_json_name
            namelist = z.namelist()
            if target_name not in namelist:
                candidates = [n for n in namelist if n.endswith("/" + inner_json_name) or n.endswith(inner_json_name)]
                if candidates:
                    target_name = candidates[0]
                else:
                    json_candidates = [n for n in namelist if n.lower().endswith(".json")]
                    if not json_candidates:
                        raise FileNotFoundError(f"No JSON file found inside {zip_path.name}")
                    target_name = json_candidates[0]

            with z.open(target_name) as jf:
                data = _json.load(jf)

    # Loaded successfully
    except Exception as e:
        print(f"Failed to load JSON from ZIP {zip_path}: {e}")
        return {"trades": [], "summary": {}}

    # ✅ Extract trades from nested structure
    trades = _extract_trades(data)

    # ✅ Extract timeframe used by the backtest if present in the JSON
    timeframe_val = None
    try:
        if isinstance(data, dict):
            # Prefer per-strategy timeframe if available
            strat_block = data.get("strategy")
            if isinstance(strat_block, dict):
                for _name, strat_obj in strat_block.items():
                    if isinstance(strat_obj, dict):
                        tf = strat_obj.get("timeframe") or strat_obj.get("ticker_interval")
                        if isinstance(tf, str) and tf:
                            timeframe_val = tf
                            break
            # Fallback to config timeframe
            if timeframe_val is None:
                cfg = data.get("config")
                if isinstance(cfg, dict):
                    tf = cfg.get("timeframe")
                    if isinstance(tf, str) and tf:
                        timeframe_val = tf
    except Exception:
        timeframe_val = None

    total = len(trades)
    wins = 0
    profit_sum = 0.0
    profit_ratio_sum = 0.0
    by_pair: Dict[str, Dict[str, float]] = {}

    for t in trades[:limit_trades]:
        pr = float(t.get("profit_ratio", 0.0) or 0.0)
        profit_ratio_sum += pr
        profit_sum += float(t.get("profit_abs", 0.0) or 0.0)
        if pr > 0:
            wins += 1
        pair = t.get("pair") or "?"
        agg = by_pair.setdefault(pair, {"count": 0, "profit_ratio_sum": 0.0, "profit_abs_sum": 0.0})
        agg["count"] += 1
        agg["profit_ratio_sum"] += pr
        agg["profit_abs_sum"] += float(t.get("profit_abs", 0.0) or 0.0)

    summary = {
        "total_trades": total,
        "winrate": (wins / total) if total else 0.0,
        "profit_abs_sum": profit_sum,
        "profit_ratio_avg": (profit_ratio_sum / total) if total else 0.0,
        "by_pair": by_pair,
        "file": f"{zip_path.name}::{inner_json_name}",
        "timeframe": timeframe_val,
    }

    # Summary computed

    return {"trades": trades[:limit_trades], "summary": summary}


def list_backtest_results(bot: Bot) -> list[dict]:
    """Return a list of available backtest artifact ZIP files for this bot.

    Each item: { file: str, mtime: float, size: int }
    """
    bot_userdir = Path(bot.userdir).resolve()
    results_dir = bot_userdir / "backtest_results"
    if not results_dir.exists():
        return []
    items: list[dict] = []
    try:
        zips = [p for p in results_dir.glob("*.zip")]
        for z in zips:
            try:
                stat = z.stat()
                items.append({
                    "file": z.name,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                })
            except Exception:
                continue
        # newest first
        items.sort(key=lambda d: d.get("mtime", 0), reverse=True)
    except Exception:
        return []
    return items


def load_backtest_result(bot: Bot, file: str, limit_trades: int = 200) -> dict:
    """Load a specific backtest result ZIP by filename and return trades + summary.

    This mirrors get_backtest_results but targets an explicit artifact.
    """
    import json as _json

    def _extract_trades(payload) -> list:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        if isinstance(payload.get("trades"), list):
            return payload["trades"]
        strategy_block = payload.get("strategy")
        if isinstance(strategy_block, dict):
            for strat_obj in strategy_block.values():
                if isinstance(strat_obj, dict) and isinstance(strat_obj.get("trades"), list):
                    return strat_obj["trades"]
        return []

    bot_userdir = Path(bot.userdir).resolve()
    results_dir = bot_userdir / "backtest_results"
    zip_path = (results_dir / file).resolve()
    if not zip_path.exists() or zip_path.suffix.lower() != ".zip":
        raise HTTPException(status_code=404, detail="Backtest artifact not found")

    inner_json_name = Path(file).stem + ".json"
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            target_name = inner_json_name
            namelist = z.namelist()
            if target_name not in namelist:
                candidates = [n for n in namelist if n.endswith("/" + inner_json_name) or n.endswith(inner_json_name)]
                if candidates:
                    target_name = candidates[0]
                else:
                    json_candidates = [n for n in namelist if n.lower().endswith(".json")]
                    if not json_candidates:
                        raise FileNotFoundError(f"No JSON file found inside {zip_path.name}")
                    target_name = json_candidates[0]
            with z.open(target_name) as jf:
                data = _json.load(jf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backtest JSON: {e}")

    trades = _extract_trades(data)

    # Extract timeframe used by the backtest if present
    timeframe_val = None
    try:
        if isinstance(data, dict):
            strat_block = data.get("strategy")
            if isinstance(strat_block, dict):
                for _name, strat_obj in strat_block.items():
                    if isinstance(strat_obj, dict):
                        tf = strat_obj.get("timeframe") or strat_obj.get("ticker_interval")
                        if isinstance(tf, str) and tf:
                            timeframe_val = tf
                            break
            if timeframe_val is None:
                cfg = data.get("config")
                if isinstance(cfg, dict):
                    tf = cfg.get("timeframe")
                    if isinstance(tf, str) and tf:
                        timeframe_val = tf
    except Exception:
        timeframe_val = None

    total = len(trades)
    wins = 0
    profit_sum = 0.0
    profit_ratio_sum = 0.0
    by_pair: Dict[str, Dict[str, float]] = {}
    for t in trades[:limit_trades]:
        pr = float(t.get("profit_ratio", 0.0) or 0.0)
        profit_ratio_sum += pr
        profit_sum += float(t.get("profit_abs", 0.0) or 0.0)
        if pr > 0:
            wins += 1
        pair = t.get("pair") or "?"
        agg = by_pair.setdefault(pair, {"count": 0, "profit_ratio_sum": 0.0, "profit_abs_sum": 0.0})
        agg["count"] += 1
        agg["profit_ratio_sum"] += pr
        agg["profit_abs_sum"] += float(t.get("profit_abs", 0.0) or 0.0)

    summary = {
        "total_trades": total,
        "winrate": (wins / total) if total else 0.0,
        "profit_abs_sum": profit_sum,
        "profit_ratio_avg": (profit_ratio_sum / total) if total else 0.0,
        "by_pair": by_pair,
        "file": file,
        "timeframe": timeframe_val,
    }
    return {"trades": trades[:limit_trades], "summary": summary}


def get_backtest_status(bot: Bot) -> dict:
    """Compute backtest status by inspecting docker containers for this bot.

    Returns:
      { state: 'idle'|'running'|'done'|'error', container?: str, started_at?: str, finished_at?: str, exit_code?: int }
    """
    names = _list_backtest_containers(bot.id)
    if not names:
        return {"state": "idle"}
    latest = names[0]
    info = _inspect_container(latest)
    running = (info.get("running") or "").lower() == "true"
    # Some docker versions report exit_code as string; coerce to int when possible
    try:
        exit_code = int(info.get("exit_code")) if info.get("exit_code") is not None else None
    except Exception:
        exit_code = None
    if running:
        return {"state": "running", "container": info.get("name") or latest, "started_at": info.get("started_at")}
    # Finished
    if exit_code is None:
        state = "done"
    else:
        state = "done" if exit_code == 0 else "error"
    return {
        "state": state,
        "container": info.get("name") or latest,
        "started_at": info.get("started_at"),
        "finished_at": info.get("finished_at"),
        "exit_code": exit_code,
    }


def tail_backtest_logs(bot: Bot, tail: int = 1000) -> dict:
    names = _list_backtest_containers(bot.id)
    latest = names[0] if names else None
    lines: List[str] = []
    if latest:
        lines = _docker_logs_tail(latest, tail=tail)
    # Fallback to host log files under user_data/logs
    if not lines:
        try:
            bot_userdir = Path(bot.userdir).resolve()
            logs_dir = bot_userdir / "logs"
            cands = [logs_dir / "backtest.out.log", logs_dir / "backtest.err.log"]
            merged: List[str] = []
            for p in cands:
                merged.extend(_tail_file_lines(p, tail))
            lines = merged[-tail:]
        except Exception:
            lines = []
    return {"container": latest, "lines": lines}


def tail_runtime_logs(bot: Bot, tail: int = 1000) -> dict:
    name = _docker_container_name(bot)
    lines = _docker_logs_tail(name, tail=tail)
    # Fallback to freqtrade log files under user_data/logs (exclude our own wrapper logs)
    if not lines:
        try:
            bot_userdir = Path(bot.userdir).resolve()
            logs_dir = bot_userdir / "logs"
            # Prefer freqtrade.log when present; else newest *.log
            prefer = logs_dir / "freqtrade.log"
            if prefer.exists():
                lines = _tail_file_lines(prefer, tail)
            else:
                # pick newest .log files, try up to 3
                files = [p for p in logs_dir.glob("*.log") if p.name not in {"bot.out.log", "bot.err.log"}]
                files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
                merged: List[str] = []
                for p in files[:3]:
                    merged.extend(_tail_file_lines(p, tail))
                lines = merged[-tail:]
        except Exception:
            lines = []
    return {"container": name, "lines": lines}


def _load_api_server_from_config(cfg_path: str) -> dict | None:
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("api_server")
    except Exception:
        return None


def _bot_freqtrade_api_base(bot: Bot) -> str | None:
    """Return base URL (http://host:port/api/v1) for the bot's Freqtrade API if enabled in config.
    Assumes listen_ip_address is reachable from this backend (ideally 127.0.0.1) and uses http.
    """
    if not bot.config_path:
        return None
    api = _load_api_server_from_config(bot.config_path) or {}
    if not api or not api.get("enabled"):
        return None
    # Always use host loopback; we publish container port to 127.0.0.1:port
    port = api.get("listen_port", 8080)
    return f"http://127.0.0.1:{port}/api/v1"


def proxy_freqtrade_api(
    bot: Bot,
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
    raw_body: bytes | None = None,
    headers: dict | None = None,
) -> tuple[int, dict | str]:
    """Forward a request to the bot's Freqtrade REST API.

    Returns (status_code, json_or_text).
    """
    base = _bot_freqtrade_api_base(bot)
    if not base:
        return 409, {"error": "Bot API server not enabled in config"}
    url = base.rstrip("/") + "/" + path.lstrip("/")
    # Read credentials for Basic Auth if provided
    api = _load_api_server_from_config(bot.config_path) or {}
    auth = None
    try:
        user = api.get("username")
        pwd = api.get("password")
        if user and pwd:
            auth = (user, pwd)
    except Exception:
        auth = None
    try:
        import importlib
        requests = importlib.import_module("requests")
    except Exception:
        return 500, {"error": "Python package 'requests' is not installed. Please install backend requirements."}
    try:
        # Only forward necessary headers (e.g., Content-Type). Avoid Host/Authorization leakage.
        fwd_headers = {}
        if headers:
            ct = headers.get("content-type") or headers.get("Content-Type")
            if ct:
                fwd_headers["Content-Type"] = ct
        # Prefer JSON when body is dict; otherwise send raw body as data
        kwargs: dict = {"params": params, "timeout": 15, "auth": auth, "headers": fwd_headers}
        if isinstance(body, dict):
            kwargs["json"] = body
        elif raw_body is not None:
            kwargs["data"] = raw_body
        resp = requests.request(method.upper(), url, **kwargs)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text
    except Exception as e:
        return 502, {"error": str(e)}


def _read_trades_from_sqlite(db_path: Path, mode_label: str, bot_id: int, limit: int | None = None) -> list[dict]:
    """Read trades from a Freqtrade SQLite file defensively.

    - db_path: path to tradesv3[.dryrun].sqlite
    - mode_label: 'live' or 'dryrun' (used to label rows and de-dupe ids)
    - bot_id: current bot id to include in rows
    - limit: optional max rows to return (applied after ordering)
    """
    if not db_path.exists():
        return []
    try:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except Exception:
        return []
    try:
        cur = conn.cursor()
        # Verify table exists
        try:
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trades'")
            if not cur.fetchone():
                return []
        except Exception:
            return []
        # Determine available columns
        cols = []
        try:
            cur.execute("PRAGMA table_info('trades')")
            cols = [r[1] for r in cur.fetchall()]
        except Exception:
            cols = []
        # Build projection with fallbacks
        def has(c: str) -> bool:
            return c in cols
        select_cols = [
            "id",
            *( ["pair"] if has("pair") else [] ),
            *( ["is_short"] if has("is_short") else [] ),
            *( ["open_date"] if has("open_date") else [] ),
            *( ["open_rate"] if has("open_rate") else [] ),
            *( ["close_date"] if has("close_date") else [] ),
            *( ["close_rate"] if has("close_rate") else [] ),
            *( ["profit_abs"] if has("profit_abs") else [] ),
            *( ["profit_ratio"] if has("profit_ratio") else [] ),
            *( ["is_open"] if has("is_open") else [] ),
            *( ["sell_reason"] if has("sell_reason") else [] ),
        ]
        if not select_cols:
            return []
        sql = f"SELECT {', '.join(select_cols)} FROM trades ORDER BY id DESC"
        if limit and isinstance(limit, int) and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = cur.execute(sql).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            rid = d.get("id")
            # Prefix id with mode to avoid collisions across DBs
            uid = f"{mode_label}:{rid}" if rid is not None else f"{mode_label}:{len(out)}"
            pair = d.get("pair")
            is_short = bool(d.get("is_short")) if "is_short" in d else False
            side = "short" if is_short else "long"
            open_date = d.get("open_date")
            close_date = d.get("close_date")
            is_open = d.get("is_open")
            status = "open" if (is_open == 1 or (is_open is True)) or (close_date in (None, "")) else "closed"
            out.append({
                "id": uid,
                "bot_id": bot_id,
                "mode": mode_label,
                "pair": pair,
                "side": side,
                "open_rate": d.get("open_rate"),
                "close_rate": d.get("close_rate"),
                "profit_abs": d.get("profit_abs"),
                "profit_ratio": d.get("profit_ratio"),
                "open_date": open_date,
                "close_date": close_date,
                "status": status,
                "sell_reason": d.get("sell_reason"),
            })
        return out
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_trades_history(user: User, bot: Bot, mode: str | None = None, limit: int | None = None) -> list[dict]:
    """Aggregate trades from the bot's local SQLite databases.

    - mode: 'live' | 'dryrun' | 'all' (default 'all')
    - limit: optional max rows per DB (applied per selected DB)
    Returns a merged, newest-first list with a 'mode' field per row.
    """
    bot_userdir = Path(bot.userdir).resolve()
    targets: list[tuple[Path, str]] = []
    m = (mode or "all").lower()
    live_db = bot_userdir / "tradesv3.sqlite"
    dry_db = bot_userdir / "tradesv3.dryrun.sqlite"
    if m in ("live",):
        targets.append((live_db, "live"))
    elif m in ("dry", "dryrun"):
        targets.append((dry_db, "dryrun"))
    else:
        # all
        targets.append((live_db, "live"))
        targets.append((dry_db, "dryrun"))
    all_rows: list[dict] = []
    for path, label in targets:
        all_rows.extend(_read_trades_from_sqlite(path, label, bot.id, limit=limit))
    # Merge-sort by open_date desc then id if present
    def sort_key(d: dict):
        # open_date may be ISO string or None; sort None last
        od = d.get("open_date") or ""
        return (od, str(d.get("id") or ""))
    all_rows.sort(key=sort_key, reverse=True)
    return all_rows


def _import_strategy_timeframes(cfg_path: str) -> list[str]:
    """Read timeframes from the composed config only.

    - Returns unique list of timeframes based on config fields (e.g., 'timeframe').
    - No dynamic imports, no regex parsing, and no implicit fallback to any default.
    - If nothing is configured, returns an empty list and the caller can decide how to proceed.
    """
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
    except Exception:
        return []
    tfs: list[str] = []
    seen: set[str] = set()
    def _add(tf: str):
        s = (tf or "").strip()
        if s and s not in seen:
            seen.add(s)
            tfs.append(s)
    # Primary timeframe
    tf = cfg.get("timeframe")
    if isinstance(tf, str):
        _add(tf)
    # Optional: a list of additional/informative timeframes the strategy needs
    for key in ("informative_timeframes", "timeframes"):
        itfs = cfg.get(key)
        if isinstance(itfs, list):
            for t in itfs:
                if isinstance(t, str):
                    _add(t)
    # Best-effort: also read timeframe(s) from the Strategy class if available.
    try:
        strat_name = cfg.get("strategy")
        spath = cfg.get("strategy_path")
        if isinstance(strat_name, str) and strat_name and strat_name != "__SET_YOUR_STRATEGY__":
            cfg_file = Path(cfg_path).resolve()
            bot_userdir = cfg_file.parent.parent if cfg_file.parent.name == "configs" else cfg_file.parent
            # Derive user root (workspaces/<user>/user) if present in path
            user_root: Path | None = None
            try:
                parts = list(bot_userdir.parts)
                if "workspaces" in parts:
                    idx = parts.index("workspaces")
                    if idx + 1 < len(parts):
                        user_root = Path(*parts[: idx + 2]) / "user"
            except Exception:
                user_root = None
            search_roots: list[Path] = []
            # Strategy path resolution
            try:
                if isinstance(spath, str) and spath:
                    p = Path(spath)
                    if p.is_absolute():
                        search_roots.append(p)
                    else:
                        search_roots.append((bot_userdir / p).resolve())
            except Exception:
                pass
            # Common strategy locations
            try:
                if user_root and (user_root / "strategies").exists():
                    search_roots.append(user_root / "strategies")
                if user_root and (user_root / "strategies" / "variants").exists():
                    search_roots.append(user_root / "strategies" / "variants")
            except Exception:
                pass
            try:
                if (bot_userdir / "strategies").exists():
                    search_roots.append(bot_userdir / "strategies")
            except Exception:
                pass
            # Find strategy file
            candidates: list[Path] = []
            try:
                for root in search_roots:
                    if not root.exists():
                        continue
                    for dirpath, _, filenames in os.walk(root):
                        for fn in filenames:
                            if fn.lower() == f"{strat_name.lower()}.py":
                                candidates.append(Path(dirpath) / fn)
                if not candidates:
                    # Non-recursive attempt
                    for root in search_roots:
                        candidates.append(root / f"{strat_name}.py")
                candidates = [c for c in candidates if c.exists()]
            except Exception:
                candidates = []
            # Import and read attributes
            for fpath in candidates:
                try:
                    import importlib.util as _ilu
                    spec = _ilu.spec_from_file_location(strat_name, str(fpath))
                    if spec and spec.loader:
                        mod = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(mod)  # type: ignore
                        cls = getattr(mod, strat_name, None)
                        if cls is None:
                            continue
                        # Primary timeframe attributes
                        for attr in ("timeframe", "ticker_interval"):
                            val = getattr(cls, attr, None)
                            if isinstance(val, str):
                                _add(val)
                        # Additional timeframe lists
                        for attr in ("informative_timeframes", "timeframes"):
                            vals = getattr(cls, attr, None)
                            if isinstance(vals, list):
                                for v in vals:
                                    if isinstance(v, str):
                                        _add(v)
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return tfs


def download_data(db: Session, user: User, bot: Bot, timerange: str, pairs_override: Optional[List[str]] = None, timeframes_override: Optional[List[str]] = None, sync: bool = False) -> dict:
    """Download market data for backstaging using bot's config and strategy.

    - Always uses Binance as the data source.
    - Derives pairs from composed config (pairs or pair_whitelist).
    - Derives timeframes from the strategy class (timeframe and optional informative_timeframe).
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()
    # Compose config (to read pairs/strategy)
    try:
        active_strategy_spec = None
        if getattr(bot, "active_strategy", None):
            active_strategy_spec = json.loads(bot.active_strategy)
    except Exception:
        active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        cfg_path = compose_runtime_config(str(bot_userdir))

    # Read pairs from override or config
    pairs: list[str] = []
    if pairs_override and isinstance(pairs_override, list) and len(pairs_override) > 0:
        pairs = [str(p).strip() for p in pairs_override if str(p).strip()]
    else:
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg.get("pairs"), list):
                pairs = cfg.get("pairs") or []
            elif isinstance(cfg.get("pair_whitelist"), list):
                pairs = cfg.get("pair_whitelist") or []
        except Exception:
            pairs = []
    if not pairs:
        raise HTTPException(status_code=422, detail="No pairs configured in bot config. Set pair_whitelist or pairs.")

    # Discover timeframes from override or strategy
    if timeframes_override and isinstance(timeframes_override, list) and len(timeframes_override) > 0:
        timeframes = [str(t).strip() for t in timeframes_override if str(t).strip()]
    else:
        timeframes = _import_strategy_timeframes(str(cfg_path))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "download-data.out.log"
    err_log = logs_dir / "download-data.err.log"

    if not _docker_available():
        raise HTTPException(status_code=503, detail="Docker is not available on this host.")

    # Normalize timerange so forms like "-90d" are accepted (converted to YYYYMMDD-)
    try:
        timerange = _normalize_timerange(timerange)
    except Exception:
        pass

    # Detect trading mode (spot/futures) from generated config to set candle-type
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            _cfgjson = json.load(f)
        _tmode = str((_cfgjson.get("trading_mode") or "spot")).lower()
    except Exception:
        _tmode = "spot"
    _candle_type = "futures" if _tmode == "futures" else "spot"

    if sync:
        # Run blocking to ensure data exists before returning
        try:
            # Normalize pairs for market if needed (e.g., Binance Futures requires :<QUOTE> suffix)
            norm_pairs = _normalize_pairs_for_market(pairs, _candle_type, "binance")
            _download_data_sync(Path(user_root), bot_userdir, "binance", norm_pairs, timeframes, timerange, candle_type=_candle_type)
        except HTTPException:
            # Already enriched with stderr tail
            raise
        except Exception as e:
            # Include stderr tail when possible
            try:
                err_log = (bot_userdir / "logs" / "download-data.err.log")
                data = err_log.read_bytes()[-2048:]
                tail = data.decode("utf-8", errors="ignore").strip().splitlines()
                last = tail[-1] if tail else str(e)
                raise HTTPException(status_code=502, detail={"message": "download-data failed", "error": last})
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=502, detail={"message": "download-data failed", "error": str(e)})
        return {
            "status": "completed",
            "pairs": pairs,
            "timeframes": timeframes,
            "timerange": timerange,
            "logs": {
                "stdout": str(out_log),
                "stderr": str(err_log),
            },
        }

    # no host branch; run detached and return immediately
    # Build docker command for download-data
    name = f"ft-dl-{bot.id}-{int(time.time())}"
    extra_strategy_dir = Path(user_root) / "strategies"
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    docker_py_path = "/freqtrade/user_data:/repo"
    volumes = [f"{str(bot_userdir)}:/freqtrade/user_data", f"{str(repo_root)}:/repo"]
    if extra_strategy_dir and extra_strategy_dir.exists():
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/extra_strategies")
        docker_py_path = f"{docker_py_path}:/freqtrade/extra_strategies"
    image = _get_freqtrade_image()
    _docker_image_ensure(image, out_log)
    cmd = ["docker", "run", "-d", "--name", name]
    for v in volumes:
        cmd += ["-v", v]
    cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
    # Ensure headless matplotlib backend for async data downloads as well
    cmd += ["-e", "MPLBACKEND=Agg"]
    cmd += [
        image,
        "download-data",
        "--exchange", "binance",
        "--timerange", timerange,
        "--userdir", "/freqtrade/user_data",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
    ]
    # In async path, prefer to prepend to ensure earlier requested ranges are fetched if local data already exists
    cmd += ["--prepend"]
    if _candle_type == "futures":
        # Do not pass '--candle-type' to download-data (flag may be unsupported);
        # rely on trading_mode in config and normalized pair symbols.
        # Normalize pairs for Binance Futures contract notation
        pairs = _normalize_pairs_for_market(pairs, _candle_type, "binance")
    if timeframes:
        cmd += ["-t", *timeframes]
    if pairs:
        cmd += ["-p", *pairs]

    # Env setup similar to start_bot
    env = os.environ.copy()
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    py_path_parts = [str(user_root), str(repo_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(py_path_parts)
    _log_command(out_log, cmd, {"PYTHONPATH": env["PYTHONPATH"]})

    with out_log.open("ab") as out, err_log.open("ab") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )

    return {
        "status": "started",
        "pid": proc.pid,
        "pairs": pairs,
        "timeframes": timeframes,
        "timerange": timerange,
        "logs": {
            "stdout": str(out_log),
            "stderr": str(err_log),
        },
        "args": cmd,
    }


def get_runtime_info(db: Session, user: User, bot: Bot) -> dict:
    """Return effective runtime details for troubleshooting.

    Includes runtime mode (host/docker), container name (if docker), API host/port/base, running state, and config path.
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()
    runtime = "docker"
    container = _docker_container_name(bot)

    # Determine config path to read API server details
    cfg_path: Optional[str] = None
    if getattr(bot, "config_path", None):
        cfg_path = bot.config_path
    else:
        try:
            active_strategy_spec = None
            if getattr(bot, "active_strategy", None):
                active_strategy_spec = json.loads(bot.active_strategy)
        except Exception:
            active_strategy_spec = None
        try:
            cfg_path = str(
                compose_bot_config(
                    str(user_root),
                    str(bot_userdir),
                    mode=getattr(bot, "mode", None),
                    active_strategy=active_strategy_spec,
                )
            )
        except Exception:
            try:
                cfg_path = str(compose_runtime_config(str(bot_userdir)))
            except Exception:
                cfg_path = None

    api_host: Optional[str] = None
    api_port: Optional[int] = None
    api_base: Optional[str] = None
    effective_strategy: Optional[str] = None
    effective_strategy_path: Optional[str] = None
    active_strategy_meta: Optional[dict] = None
    if cfg_path:
        # Load generated config to derive API and effective strategy information
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                _cfgjson = json.load(f) or {}
        except Exception:
            _cfgjson = {}
        api_cfg = (_cfgjson.get("api_server") or {}) if isinstance(_cfgjson, dict) else {}
        # Report host-side address
        api_host = "127.0.0.1"
        try:
            api_port = int(api_cfg.get("listen_port", 8080)) if isinstance(api_cfg, dict) else 8080
        except Exception:
            api_port = 8080
        api_base = f"http://{api_host}:{api_port}/api/v1"
        # Strategy details
        try:
            effective_strategy = _cfgjson.get("strategy")
            effective_strategy_path = _cfgjson.get("strategy_path")
            # Look for active_strategy in multiple meta locations
            active_strategy_meta = (
                (_cfgjson.get("meta") or {}).get("active_strategy")
                or ((_cfgjson.get("custom_info") or {}).get("meta") or {}).get("active_strategy")
                or ((_cfgjson.get("strategy_parameters") or {}).get("meta") or {}).get("active_strategy")
            )
        except Exception:
            pass

    # Determine running state
    running: Optional[bool] = None
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    running = _docker_is_running(container) if container else False

    return {
        "runtime": runtime,
        "container_name": container,
        "api_host": api_host,
        "api_port": api_port,
        "api_base": api_base,
        "strategy": effective_strategy,
        "strategy_path": effective_strategy_path,
        "active_strategy": active_strategy_meta,
        "effective_strategy": (active_strategy_meta.get("clazz") if isinstance(active_strategy_meta, dict) and active_strategy_meta.get("clazz") else effective_strategy),
        "running": running,
        "config_path": cfg_path,
    }


# Backward compatibility wrapper (deprecated)
def start_user_level_bot(db: Session, user: User, config_path: Optional[str] = None):  # pragma: no cover
    raise RuntimeError("User-level bot start deprecated. Use per-bot /users/{id}/bots/{bot_id}/start endpoint.")
