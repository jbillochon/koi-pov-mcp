"""
TI v2 sources: OSV.dev (package vulnerabilities by ecosystem/name/version),
CISA KEV (known exploited), FIRST EPSS (exploitation probability).

All deterministic, free, keyless, batch-friendly. No LLM anywhere: these are
facts to be cited, with a fetched_at date, under the skill's language
hierarchy (KEV > EPSS > CVSS).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"
KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)
EPSS_URL = "https://api.first.org/data/v1/epss"

UA = {"User-Agent": "koi-pov-mcp/0.7"}

# Koi marketplace slug -> OSV ecosystem. Only ecosystems OSV actually indexes;
# anything else is skipped rather than guessed.
SLUG_TO_OSV = {
    "npm": "npm",
    "pypi": "PyPI",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_packages(report: dict, limit: int = 40) -> list[dict]:
    """High-interest items with an OSV-queryable ecosystem and a version.
    Sources: action_candidates (carry marketplace_slug), then malicious items
    that also carry a slug."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for it in (report.get("action_candidates") or []) + (report.get("malicious_items") or []):
        slug = it.get("marketplace_slug")
        eco = SLUG_TO_OSV.get(slug or "")
        name, version = it.get("name"), it.get("version")
        if not (eco and name and version):
            continue
        key = (eco, name, version)
        if key in seen:
            continue
        seen.add(key)
        out.append({"ecosystem": eco, "name": name, "version": version})
        if len(out) >= limit:
            break
    return out


def osv_query(packages: list[dict], timeout: int = 30) -> tuple[dict, list[str]]:
    """Batch-query OSV. Returns ({pkg_label: [vuln ids]}, [errors])."""
    if not packages:
        return {}, []
    queries = [
        {"package": {"name": p["name"], "ecosystem": p["ecosystem"]},
         "version": p["version"]}
        for p in packages
    ]
    try:
        resp = requests.post(
            OSV_BATCH, json={"queries": queries}, timeout=timeout, headers=UA
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {}, [f"osv querybatch: {exc}"]
    results = resp.json().get("results") or []
    out: dict[str, list[str]] = {}
    for p, res in zip(packages, results):
        vulns = [v.get("id") for v in (res or {}).get("vulns") or [] if v.get("id")]
        if vulns:
            label = f"{p['name']}@{p['version']} ({p['ecosystem']})"
            out[label] = vulns
    return out, []


def osv_details(vuln_id: str, timeout: int = 20) -> dict | None:
    """Fetch one OSV record; used to resolve CVE aliases and a summary."""
    try:
        resp = requests.get(OSV_VULN.format(vuln_id), timeout=timeout, headers=UA)
        if resp.status_code >= 400:
            return None
        d = resp.json()
        return {
            "id": d.get("id"),
            "aliases": [a for a in d.get("aliases") or [] if a.startswith("CVE-")],
            "summary": (d.get("summary") or "")[:400],
        }
    except requests.RequestException:
        return None


def fetch_kev(timeout: int = 30) -> tuple[dict[str, str], list[str]]:
    """CISA KEV catalog: {cve_id: date_added}. One fetch, no key."""
    try:
        resp = requests.get(KEV_URL, timeout=timeout, headers=UA)
        resp.raise_for_status()
        vulns = resp.json().get("vulnerabilities") or []
        return {
            v["cveID"].upper(): v.get("dateAdded", "")
            for v in vulns if v.get("cveID")
        }, []
    except (requests.RequestException, ValueError) as exc:
        return {}, [f"kev: {exc}"]


def fetch_epss(cve_ids: list[str], timeout: int = 30) -> tuple[dict[str, dict], list[str]]:
    """EPSS scores, batched 100 per call: {cve: {epss, percentile}}."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    for i in range(0, len(cve_ids), 100):
        chunk = cve_ids[i:i + 100]
        try:
            resp = requests.get(
                EPSS_URL, params={"cve": ",".join(chunk)}, timeout=timeout, headers=UA
            )
            resp.raise_for_status()
            for row in resp.json().get("data") or []:
                out[row["cve"].upper()] = {
                    "epss": float(row.get("epss") or 0),
                    "percentile": float(row.get("percentile") or 0),
                }
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"epss chunk {i // 100}: {exc}")
    return out, errors
