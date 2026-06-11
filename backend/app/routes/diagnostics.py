from __future__ import annotations

import socket
from fastapi import APIRouter, Depends
import requests

from ..auth import get_current_user

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _safe_get(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=5)
        if r.ok:
            return (r.text or "").strip()
        return None
    except Exception:
        return None


@router.get("/egress")
def get_egress_info(current=Depends(get_current_user)) -> dict:
    """Report egress IPs as seen externally (IPv4/IPv6) and Binance DNS resolution.

    Helps determine the exact address to whitelist on Binance.
    """
    ipv4 = _safe_get("https://ipv4.icanhazip.com") or _safe_get("https://api.ipify.org")
    ipv6 = _safe_get("https://ipv6.icanhazip.com") or _safe_get("https://api64.ipify.org")

    # Resolve Binance API hostnames to see available address families from this environment
    def _resolve_host(host: str) -> list[dict]:
        results: list[dict] = []
        try:
            infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            for family, socktype, proto, canonname, sockaddr in infos:
                ip = sockaddr[0]
                results.append({
                    "family": "IPv6" if family == socket.AF_INET6 else "IPv4",
                    "ip": ip,
                })
        except Exception:
            pass
        # Deduplicate
        seen = set()
        uniq = []
        for r in results:
            key = (r["family"], r["ip"]) 
            if key not in seen:
                uniq.append(r)
                seen.add(key)
        return uniq

    binance_hosts = {
        "global": "api.binance.com",
        "us": "api.binance.us",
        "spot_testnet": "testnet.binance.vision",
        "futures_testnet": "testnet.binancefuture.com",
    }
    dns = {k: _resolve_host(v) for k, v in binance_hosts.items()}

    return {
        "egress_ipv4": ipv4,
        "egress_ipv6": ipv6,
        "binance_dns": dns,
    }
