"""
Cortex XSIAM client (public API) and Koi<->XSIAM correlation.

Auth: standard API keys (Authorization: <key>, x-xdr-auth-id: <id>) and
advanced keys (sha256(key + nonce + timestamp) with x-xdr-nonce and
x-xdr-timestamp headers). Endpoints used are read-only.

Correlation v1, honest about its granularity:
- agent coverage overlap: Koi-managed hosts vs XSIAM-managed endpoints
- XSIAM incidents (last N days) landing on hosts that Koi knows
Item-level joins (which Koi finding maps to which XSIAM alert) need
per-device inventory sweeps and are a later iteration.
"""

from __future__ import annotations

import hashlib
import logging
import secrets as pysecrets
import time
from collections import Counter

import requests

log = logging.getLogger(__name__)

PAGE = 100
MAX_PAGES = 50


class XsiamError(RuntimeError):
    pass


class XsiamClient:
    def __init__(self, api_url: str, key_id: str, api_key: str,
                 advanced: bool = False, timeout: int = 60):
        self.base = api_url.rstrip("/")
        self.key_id = str(key_id)
        self.api_key = api_key
        self.advanced = advanced
        self.timeout = timeout
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        if not self.advanced:
            return {
                "x-xdr-auth-id": self.key_id,
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            }
        nonce = pysecrets.token_hex(32)
        ts = str(int(time.time() * 1000))
        auth = hashlib.sha256((self.api_key + nonce + ts).encode()).hexdigest()
        return {
            "x-xdr-auth-id": self.key_id,
            "x-xdr-nonce": nonce,
            "x-xdr-timestamp": ts,
            "Authorization": auth,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, request_data: dict) -> dict:
        url = f"{self.base}/public_api/v1{path}"
        try:
            resp = self._session.post(
                url,
                json={"request_data": request_data},
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise XsiamError(f"network error on {path}: {exc}") from exc
        if resp.status_code == 401:
            raise XsiamError(
                "401 unauthorized: check the API key, key ID, and whether the "
                "key is standard or advanced."
            )
        if resp.status_code >= 400:
            raise XsiamError(f"{resp.status_code} on {path}: {resp.text[:300]}")
        return (resp.json() or {}).get("reply") or {}

    def ping(self) -> bool:
        self._post("/endpoints/get_endpoint/", {"search_from": 0, "search_to": 1})
        return True

    def endpoints(self) -> list[dict]:
        out: list[dict] = []
        for page in range(MAX_PAGES):
            reply = self._post(
                "/endpoints/get_endpoint/",
                {"search_from": page * PAGE, "search_to": (page + 1) * PAGE},
            )
            batch = reply.get("endpoints") or []
            out.extend(batch)
            total = reply.get("total_count")
            if not batch or (total is not None and len(out) >= total):
                break
        return out

    def incidents(self, days: int = 30) -> list[dict]:
        since_ms = int((time.time() - days * 86400) * 1000)
        out: list[dict] = []
        for page in range(MAX_PAGES):
            reply = self._post(
                "/incidents/get_incidents/",
                {
                    "filters": [
                        {"field": "creation_time", "operator": "gte", "value": since_ms}
                    ],
                    "search_from": page * PAGE,
                    "search_to": (page + 1) * PAGE,
                },
            )
            batch = reply.get("incidents") or []
            out.extend(batch)
            total = reply.get("total_count")
            if not batch or (total is not None and len(out) >= total):
                break
        return out


def _hostname(value: str) -> str:
    return value.split(":")[0].strip().lower()


def correlate(koi_client, xsiam_client: XsiamClient, days: int = 30) -> dict:
    """Coverage overlap + incidents on Koi-known hosts. Facts only."""
    koi_hosts: set[str] = set()
    for d in koi_client.iter_devices(max_pages=40):
        name = d.get("hostname") or d.get("name") or ""
        if name:
            koi_hosts.add(name.strip().lower())

    xsiam_eps = xsiam_client.endpoints()
    xsiam_hosts = {
        (e.get("endpoint_name") or "").strip().lower()
        for e in xsiam_eps if e.get("endpoint_name")
    }

    both = koi_hosts & xsiam_hosts
    koi_only = sorted(koi_hosts - xsiam_hosts)
    xsiam_only = sorted(xsiam_hosts - koi_hosts)

    incidents = xsiam_client.incidents(days=days)
    sev = Counter()
    on_koi = Counter()
    for inc in incidents:
        sev[(inc.get("severity") or "unknown").lower()] += 1
        for h in inc.get("hosts") or []:
            hn = _hostname(h)
            if hn in koi_hosts:
                on_koi[hn] += 1

    return {
        "window_days": days,
        "coverage": {
            "koi_devices": len(koi_hosts),
            "xsiam_endpoints": len(xsiam_hosts),
            "on_both": len(both),
            "koi_only_count": len(koi_only),
            "koi_only_sample": koi_only[:15],
            "xsiam_only_count": len(xsiam_only),
            "xsiam_only_sample": xsiam_only[:15],
        },
        "incidents": {
            "total": len(incidents),
            "by_severity": dict(sev.most_common()),
            "hosts_known_to_koi_with_incidents": len(on_koi),
            "top_koi_hosts": [
                {"host": h, "incidents": c} for h, c in on_koi.most_common(10)
            ],
        },
    }
