"""
Koi Security API client.

Handles authentication, rate limiting (30 req/min/route), pagination,
and exponential backoff on 429.

Reference: https://api.prod.koi.security/api/external/v2
Origin: adapted from jbillochon/povplatform (connectors/koi/client.py),
kept dependency-free so this package deploys standalone.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.prod.koi.security"
API_PREFIX = "/api/external/v2"

# API enforces 30 requests per minute PER ROUTE.
# We stay conservative to leave headroom.
RATE_LIMIT_PER_MIN = 28
RATE_WINDOW_SEC = 60.0

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 500

MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0


class KoiAPIError(RuntimeError):
    """Raised for non-retryable API errors."""

    def __init__(self, status: int, route: str, body: str = ""):
        self.status = status
        self.route = route
        self.body = body
        super().__init__(f"Koi API {status} on {route}: {body[:400]}")


class KoiAuthError(KoiAPIError):
    """401 - bad or expired API key."""


@dataclass
class _RouteLimiter:
    """Sliding-window rate limiter, tracked per route."""

    calls: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def acquire(self, route: str) -> None:
        now = time.monotonic()
        window = self.calls[route]
        # Drop timestamps outside the window
        cutoff = now - RATE_WINDOW_SEC
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= RATE_LIMIT_PER_MIN:
            sleep_for = window[0] + RATE_WINDOW_SEC - now + 0.1
            if sleep_for > 0:
                log.info("Rate limit reached for %s, sleeping %.1fs", route, sleep_for)
                time.sleep(sleep_for)
                return self.acquire(route)

        window.append(time.monotonic())


class KoiClient:
    """
    Thin, typed-ish wrapper over the Koi external v2 API.

    Every list endpoint is exposed twice:
      - `list_x(...)`      -> single page (dict)
      - `iter_x(...)`      -> generator over all pages (yields items)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ):
        self.api_key = api_key or os.environ.get("KOI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No API key. Pass api_key= or set the KOI_API_KEY environment variable."
            )
        self.base_url = (base_url or os.environ.get("KOI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._limiter = _RouteLimiter()
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "koi-pov-mcp/0.1",
            }
        )

    # ------------------------------------------------------------------ #
    # Core request plumbing
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> Any:
        route = path  # rate limit is per-route
        url = f"{self.base_url}{API_PREFIX}{path}"

        for attempt in range(MAX_RETRIES + 1):
            self._limiter.acquire(route)
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt >= MAX_RETRIES:
                    raise KoiAPIError(0, route, f"network error: {exc}") from exc
                delay = min(BACKOFF_BASE**attempt, BACKOFF_CAP)
                log.warning("Network error on %s (attempt %d): %s", route, attempt + 1, exc)
                time.sleep(delay)
                continue

            if resp.status_code == 429:
                if attempt >= MAX_RETRIES:
                    raise KoiAPIError(429, route, "rate limited, retries exhausted")
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(BACKOFF_BASE**attempt, BACKOFF_CAP)
                log.warning("429 on %s, backing off %.1fs", route, delay)
                time.sleep(delay)
                continue

            if resp.status_code == 401:
                raise KoiAuthError(401, route, resp.text)

            if resp.status_code >= 500:
                if attempt >= MAX_RETRIES:
                    raise KoiAPIError(resp.status_code, route, resp.text)
                delay = min(BACKOFF_BASE**attempt, BACKOFF_CAP)
                log.warning("%d on %s, retrying in %.1fs", resp.status_code, route, delay)
                time.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise KoiAPIError(resp.status_code, route, resp.text)

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        raise KoiAPIError(0, route, "retries exhausted")

    def _get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json_body: dict | None = None, params: dict | None = None) -> Any:
        return self._request("POST", path, params=params, json_body=json_body)

    def _paginate(
        self,
        path: str,
        data_key: str,
        params: dict | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int | None = None,
        method: str = "GET",
        json_body: dict | None = None,
    ) -> Iterator[dict]:
        """Yield every item across all pages of a list endpoint."""
        params = dict(params or {})
        page = 1
        seen = 0
        while True:
            params["page"] = page
            params["page_size"] = min(page_size, MAX_PAGE_SIZE)

            if method == "POST":
                body = dict(json_body or {})
                body["page"] = page
                body["page_size"] = params["page_size"]
                payload = self._request("POST", path, json_body=body)
            else:
                payload = self._get(path, params)

            if payload is None:
                return

            batch = payload.get(data_key) or []
            for row in batch:
                yield row
            seen += len(batch)

            total = payload.get("total_count")
            if not batch:
                return
            if total is not None and seen >= total:
                return
            if len(batch) < params["page_size"]:
                return

            page += 1
            if max_pages and page > max_pages:
                log.warning("Stopping %s at max_pages=%d (%d items)", path, max_pages, seen)
                return

    # ------------------------------------------------------------------ #
    # Devices
    # ------------------------------------------------------------------ #

    def iter_devices(self, status: str | None = None, **kw) -> Iterator[dict]:
        params = {}
        if status:
            params["status"] = status
        yield from self._paginate("/devices", "devices", params, **kw)

    def get_device_inventory(self, device_id: str, **kw) -> Iterator[dict]:
        yield from self._paginate(f"/devices/{device_id}/inventory", "inventory", **kw)

    # ------------------------------------------------------------------ #
    # Inventory
    # ------------------------------------------------------------------ #

    def iter_inventory(
        self,
        view: str | None = None,
        marketplace: str | None = None,
        risk_level: str | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
        **kw,
    ) -> Iterator[dict]:
        params: dict[str, Any] = {}
        if view:
            params["view"] = view
        if marketplace:
            params["marketplace"] = marketplace
        if risk_level:
            params["risk_level"] = risk_level
        if sort_by:
            params["sort_by"] = sort_by
            params["sort_direction"] = sort_direction
        yield from self._paginate("/inventory", "items", params, **kw)

    def search_inventory(self, filter_group: dict, sort_by: str = "risk",
                         sort_direction: str = "desc", **kw) -> Iterator[dict]:
        body = {"filter": filter_group, "sort_by": sort_by, "sort_direction": sort_direction}
        yield from self._paginate(
            "/inventory/search", "items", method="POST", json_body=body, **kw
        )

    def get_inventory_item(self, item_id: str, marketplace: str, version: str) -> dict:
        return self._get(
            f"/inventory/{item_id}",
            {"marketplace": marketplace, "version": version},
        )

    # ------------------------------------------------------------------ #
    # Findings / Policies / Guardrails
    # ------------------------------------------------------------------ #

    def iter_findings(self, **kw) -> Iterator[dict]:
        yield from self._paginate("/findings", "items", **kw)

    def iter_policies(self, **kw) -> Iterator[dict]:
        yield from self._paginate("/policies", "policies", **kw)

    def iter_runtime_policies(self, **kw) -> Iterator[dict]:
        yield from self._paginate("/hardening/runtime-policies", "policies", **kw)

    def get_allowlist(self) -> list[dict]:
        payload = self._get("/policies/allowlist")
        return (payload or {}).get("items", [])

    def get_blocklist(self) -> list[dict]:
        payload = self._get("/policies/blocklist")
        return (payload or {}).get("items", [])

    # ------------------------------------------------------------------ #
    # Remediations / Approvals / Alerts / Audit
    # ------------------------------------------------------------------ #

    def iter_remediations(self, status: str | None = None, **kw) -> Iterator[dict]:
        params = {}
        if status:
            params["status"] = status
        yield from self._paginate("/remediations", "items", params, **kw)

    def iter_approval_requests(self, approval_status: str | None = None, **kw) -> Iterator[dict]:
        params = {}
        if approval_status:
            params["approval_status"] = approval_status
        yield from self._paginate("/approval-requests", "items", params, **kw)

    def iter_alerts(
        self,
        alert_type: str | None = None,
        created_at_gte: str | None = None,
        created_at_lte: str | None = None,
        **kw,
    ) -> Iterator[dict]:
        params = {}
        if alert_type:
            params["alert_type"] = alert_type
        if created_at_gte:
            params["created_at_gte"] = created_at_gte
        if created_at_lte:
            params["created_at_lte"] = created_at_lte
        yield from self._paginate("/alerts", "alerts", params, **kw)

    def iter_audit_logs(
        self,
        created_at_gte: str | None = None,
        created_at_lte: str | None = None,
        types: list[str] | None = None,
        **kw,
    ) -> Iterator[dict]:
        params: dict[str, Any] = {}
        if created_at_gte:
            params["created_at_gte"] = created_at_gte
        if created_at_lte:
            params["created_at_lte"] = created_at_lte
        if types:
            params["types"] = types
        yield from self._paginate("/audit-logs", "items", params, **kw)

    # ------------------------------------------------------------------ #
    # Agent Activity  (windows are capped: events 24h, sessions 30d)
    # ------------------------------------------------------------------ #

    def iter_agent_sessions(
        self,
        created_at_gte: str,
        created_at_lte: str,
        verdict: str | None = None,
        agent: str | None = None,
        **kw,
    ) -> Iterator[dict]:
        params = {"created_at_gte": created_at_gte, "created_at_lte": created_at_lte}
        if verdict:
            params["verdict"] = verdict
        if agent:
            params["agent"] = agent
        yield from self._paginate("/agent-activity/sessions", "data", params, **kw)

    def iter_agent_events(
        self,
        created_at_gte: str,
        created_at_lte: str,
        session_id: str | None = None,
        **kw,
    ) -> Iterator[dict]:
        """NOTE: the API caps this window at 24 hours."""
        params = {"created_at_gte": created_at_gte, "created_at_lte": created_at_lte}
        if session_id:
            params["session_id"] = session_id
        yield from self._paginate("/agent-activity/events", "data", params, **kw)

    # ------------------------------------------------------------------ #
    # Groups / Users
    # ------------------------------------------------------------------ #

    def iter_groups(self, **kw) -> Iterator[dict]:
        yield from self._paginate("/groups", "groups", **kw)

    def get_users(self) -> list[dict]:
        payload = self._get("/users")
        return (payload or {}).get("users", [])

    # ------------------------------------------------------------------ #
    # Connectivity check
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Cheap auth/connectivity probe."""
        self._get("/devices", {"page": 1, "page_size": 1})
        return True
