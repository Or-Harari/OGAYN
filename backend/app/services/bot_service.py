from __future__ import annotations

import os
import subprocess
import json
import time
from pathlib import Path
from typing import Optional

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
        out = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True)
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


def _containerize_strategy_path(user_root: Path, bot_userdir: Path, host_path: str | None) -> str | None:
    """Translate a host strategy path to the container mount path.

    - If under bot_userdir -> /freqtrade/user_data/<relative>
    - If under user_root/user/strategies -> /freqtrade/extra_strategies/<relative>
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
    # We mount /freqtrade/extra_strategies to either <user>/user/strategies/variants (preferred) or <user>/user/strategies
    preferred = (user_root / "user" / "strategies" / "variants").resolve()
    extra_base = preferred if preferred.exists() else (user_root / "user" / "strategies").resolve()
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
    # Ensure strategy presence prior to running
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_json = json.load(f)
        if not cfg_json.get("strategy"):
            raise HTTPException(status_code=422, detail="Strategy not set in composed config. Please specify a concrete strategy class name.")
    except HTTPException:
        raise
    except Exception:
        cfg_json = {}
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
    # Strategy extras mount
    # Prefer shared 'variants' folder if present, else fall back to 'strategies'
    extra_strategy_dir = Path(user_root) / "user" / "strategies" / "variants"
    if not extra_strategy_dir.exists():
        extra_strategy_dir = Path(user_root) / "user" / "strategies"
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
        "-p", f"127.0.0.1:{host_port}:8080",
    ]
    for v in volumes:
        cmd += ["-v", v]
    cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
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
    with out_log.open("ab") as out, err_log.open("ab") as err:
        subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
        )
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
    return {
        "status": "running" if running else (rec.status if rec else "stopped"),
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

    # Build docker command for backtesting
    name = f"ft-bt-{bot.id}-{int(time.time())}"
    extra_strategy_dir = Path(user_root) / "user" / "strategies" / "variants"
    if not extra_strategy_dir.exists():
        extra_strategy_dir = Path(user_root) / "user" / "strategies"
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
    cmd += [
        image,
        "backtesting",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
        "--userdir", "/freqtrade/user_data",
    ]
    # Remap strategy_path for backtesting as well (if strategy_path exists in config)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            _cfgjson = json.load(f)
        _spath = _containerize_strategy_path(user_root, bot_userdir, _cfgjson.get("strategy_path"))
        if _spath:
            cmd += ["--strategy-path", _spath]
    except Exception:
        pass
    if params.strategy:
        cmd += ["--strategy", params.strategy]
    if params.timerange:
        cmd += ["--timerange", params.timerange]
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
    host = api.get("listen_ip_address", "127.0.0.1")
    port = api.get("listen_port", 8080)
    return f"http://{host}:{port}/api/v1"


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


def _import_strategy_timeframes(cfg_path: str) -> list[str]:
    """Best-effort import of strategy class to read timeframe and optional informative_timeframe.

    Returns a list of unique timeframes. Falls back to ["5m"] if not discoverable.
    """
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        strat = cfg.get("strategy")
        spath = cfg.get("strategy_path")
        if not strat or not spath:
            return ["5m"]
        strat_file = Path(spath) / f"{strat}.py"
        if not strat_file.exists():
            return ["5m"]
        import importlib.util, sys, re
        # Temporarily extend sys.path with strategy_path and repo root so imports in the strategy work
        add_paths: list[str] = []
        try:
            add_paths.append(str(Path(spath)))
        except Exception:
            pass
        try:
            file_path = Path(__file__).resolve()
            repo_root = file_path.parents[3] if len(file_path.parents) >= 4 else file_path.parent
            add_paths.append(str(repo_root))
        except Exception:
            pass
        original_sys_path = list(sys.path)
        try:
            for p in add_paths:
                if p and p not in sys.path:
                    sys.path.insert(0, p)
            spec = importlib.util.spec_from_file_location(strat, str(strat_file))
            if spec is None or spec.loader is None:
                raise RuntimeError("spec not loadable")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            cls = getattr(mod, strat, None)
            if cls is None:
                raise RuntimeError("class not found")
            tfs: list[str] = []
            if hasattr(cls, "timeframe") and isinstance(getattr(cls, "timeframe"), str):
                tfs.append(getattr(cls, "timeframe"))
            if hasattr(cls, "informative_timeframe") and isinstance(getattr(cls, "informative_timeframe"), str):
                tfs.append(getattr(cls, "informative_timeframe"))
            uniq: list[str] = []
            for tf in tfs:
                if tf and tf not in uniq:
                    uniq.append(tf)
            if uniq:
                return uniq
            # Fallthrough to regex parse if empty
            raise RuntimeError("no timeframe attributes")
        except Exception:
            # Regex fallback: parse timeframe variables without executing imports
            try:
                content = strat_file.read_text(encoding="utf-8", errors="ignore")
                m1 = re.search(r"^\s*timeframe\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
                m2 = re.search(r"^\s*informative_timeframe\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
                vals: list[str] = []
                if m1:
                    vals.append(m1.group(1))
                if m2:
                    vals.append(m2.group(1))
                return vals or ["5m"]
            except Exception:
                return ["5m"]
        finally:
            sys.path = original_sys_path
    except Exception:
        return ["5m"]


def download_data(db: Session, user: User, bot: Bot, timerange: str) -> dict:
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

    # Read pairs from config
    pairs: list[str] = []
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

    # Discover timeframes from strategy
    timeframes = _import_strategy_timeframes(str(cfg_path))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "download-data.out.log"
    err_log = logs_dir / "download-data.err.log"

    if not _docker_available():
        raise HTTPException(status_code=503, detail="Docker is not available on this host.")
    # no host branch

    # Build docker command for download-data
    name = f"ft-dl-{bot.id}-{int(time.time())}"
    _candidates = [
        Path(user_root) / "user" / "strategies" / "variants",
        Path(user_root) / "strategies" / "variants",
        Path(user_root) / "user" / "strategies",
        Path(user_root) / "strategies",
    ]
    extra_strategy_dir = next((p for p in _candidates if p.exists()), None)
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
    cmd += [
        image,
        "download-data",
        "--exchange", "binance",
        f"--timerange={timerange}",
        "--userdir", "/freqtrade/user_data",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
    ]
    for tf in timeframes:
        cmd += ["-t", tf]
    for p in pairs:
        cmd += ["-p", p]

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
    if cfg_path:
        api_cfg = _load_api_server_from_config(cfg_path) or {}
        api_host = api_cfg.get("listen_ip_address", "127.0.0.1") if isinstance(api_cfg, dict) else "127.0.0.1"
        try:
            api_port = int(api_cfg.get("listen_port", 8080)) if isinstance(api_cfg, dict) else 8080
        except Exception:
            api_port = 8080
        api_base = f"http://{api_host}:{api_port}/api/v1"

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
        "running": running,
        "config_path": cfg_path,
    }


# Backward compatibility wrapper (deprecated)
def start_user_level_bot(db: Session, user: User, config_path: Optional[str] = None):  # pragma: no cover
    raise RuntimeError("User-level bot start deprecated. Use per-bot /users/{id}/bots/{bot_id}/start endpoint.")
