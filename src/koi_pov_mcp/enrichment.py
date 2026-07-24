"""
Deterministic threat-intel enrichment.

CVE records come from the NVD public API. MITRE technique suggestions are a
static mapping from Koi finding identifiers, not a model guess, so a technique
shown to a customer traces back to a rule someone wrote deliberately.

No LLM here by design: in the MCP context the narrative layer is Claude
itself, governed by the skill's rules. This module only supplies facts.

Origin: ported from jbillochon/povplatform (intelligence/enrichment.py).
Optional NVD_API_KEY env var raises the NVD rate limit (50 req/30s instead
of 5 req/30s for unauthenticated calls).
"""

from __future__ import annotations

import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

# Unauthenticated NVD allows 5 requests per 30 seconds; with an API key, 50.
NVD_DELAY_UNAUTH = 6.5
NVD_DELAY_AUTH = 1.2


# Koi finding identifiers to MITRE ATT&CK techniques. Kept explicit so that
# every technique in a report is one a human chose, not one a model produced.
FINDING_TO_MITRE: dict[str, list[str]] = {
    "malware_detected": ["T1195.002"],
    "malicious_activity_detected": ["T1195.002", "T1059"],
    "associated_with_malicious_campaign": ["T1195.002"],
    "removed_from_marketplace": ["T1195.002"],
    "transfer_of_ownership": ["T1195.002"],
    "data_exfiltration": ["T1567.002"],
    "credential_access": ["T1555.005", "T1552.001"],
    "secrets_in_code": ["T1552.001"],
    "reads_credentials": ["T1555"],
    "broad_host_permissions": ["T1176"],
    "code_execution_permissions": ["T1059"],
    "network_interception_permissions": ["T1557"],
    "bypasses_network_control": ["T1090"],
    "external_communication": ["T1071.001"],
    "clipboard_access": ["T1115"],
    "screen_capture": ["T1113"],
    "obfuscated_code": ["T1027"],
    "typosquatting": ["T1195.002"],
    "vulnerable_dependency": ["T1195.001"],
    "unverified_publisher": ["T1195.002"],
    "individual_publisher": ["T1195.002"],
    "collection_of_pii": ["T1119"],
    "unrestricted_network_access": ["T1071"],
    "no_authentication": ["T1078"],
}

MITRE_NAMES: dict[str, str] = {
    "T1027": "Obfuscated Files or Information",
    "T1059": "Command and Scripting Interpreter",
    "T1059.004": "Unix Shell",
    "T1071": "Application Layer Protocol",
    "T1071.001": "Web Protocols",
    "T1078": "Valid Accounts",
    "T1090": "Proxy",
    "T1113": "Screen Capture",
    "T1115": "Clipboard Data",
    "T1119": "Automated Collection",
    "T1176": "Browser Extensions",
    "T1195.001": "Compromise Software Dependencies and Development Tools",
    "T1195.002": "Compromise Software Supply Chain",
    "T1552.001": "Credentials In Files",
    "T1555": "Credentials from Password Stores",
    "T1555.005": "Password Managers",
    "T1557": "Adversary-in-the-Middle",
    "T1567.002": "Exfiltration to Cloud Storage",
}


def extract_cve_ids(report: dict, limit: int = 20) -> list[str]:
    """Find CVE identifiers mentioned anywhere in a snapshot."""
    found: set[str] = set()

    def scan(value):
        if isinstance(value, str):
            for match in CVE_PATTERN.findall(value):
                found.add(match.upper())
        elif isinstance(value, dict):
            for v in value.values():
                scan(v)
        elif isinstance(value, list):
            for v in value:
                scan(v)

    for key in (
        "top_risk_items",
        "action_candidates",
        "malicious_items",
        "finding_frequency",
    ):
        scan(report.get(key))

    return sorted(found)[:limit]


def fetch_cve(cve_id: str, timeout: int = 20) -> dict | None:
    """Fetch one CVE record from the NVD."""
    headers = {"User-Agent": "koi-pov-mcp/0.5"}
    api_key = os.environ.get("NVD_API_KEY", "")
    if api_key:
        headers["apiKey"] = api_key
    try:
        response = requests.get(
            NVD_API,
            params={"cveId": cve_id},
            timeout=timeout,
            headers=headers,
        )
        if response.status_code == 404:
            return None
        if response.status_code == 403:
            log.warning("NVD rate limit hit for %s", cve_id)
            return None
        if response.status_code >= 400:
            log.warning("NVD returned %s for %s", response.status_code, cve_id)
            return None

        vulns = response.json().get("vulnerabilities") or []
        if not vulns:
            return None
        cve = vulns[0].get("cve", {})

        description = ""
        for d in cve.get("descriptions", []):
            if d.get("lang") == "en":
                description = d.get("value", "")
                break

        metrics = cve.get("metrics", {})
        score = severity = vector = None
        for version in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            entries = metrics.get(version)
            if entries:
                data = entries[0].get("cvssData", {})
                score = data.get("baseScore")
                severity = data.get("baseSeverity") or entries[0].get("baseSeverity")
                vector = data.get("vectorString")
                break

        weaknesses = []
        for w in cve.get("weaknesses", []):
            for d in w.get("description", []):
                if d.get("value", "").startswith("CWE-"):
                    weaknesses.append(d["value"])

        return {
            "id": cve.get("id", cve_id),
            "description": description[:900],
            "cvss_score": score,
            "cvss_severity": severity,
            "cvss_vector": vector,
            "cwe": sorted(set(weaknesses))[:5],
            "published": cve.get("published"),
            "last_modified": cve.get("lastModified"),
        }
    except requests.RequestException as exc:
        log.warning("Could not reach the NVD for %s: %s", cve_id, exc)
        return None


def map_findings_to_mitre(report: dict) -> dict[str, dict]:
    """Map the findings present in a snapshot to MITRE techniques."""
    out: dict[str, dict] = {}

    def normalise(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")

    seen: set[str] = set()
    for entry in report.get("finding_frequency") or []:
        if isinstance(entry, dict) and entry.get("finding"):
            seen.add(normalise(entry["finding"]))
    for key in ("top_risk_items", "action_candidates"):
        for item in report.get(key) or []:
            for f in (item or {}).get("findings") or []:
                seen.add(normalise(f if isinstance(f, str) else f.get("finding_id", "")))

    for finding in seen:
        techniques = FINDING_TO_MITRE.get(finding)
        if not techniques:
            # Try a looser match, so "malware_detected_v2" still maps.
            for known, mapped in FINDING_TO_MITRE.items():
                if known in finding or finding in known:
                    techniques = mapped
                    break
        if techniques:
            out[finding] = {
                "techniques": [
                    {"id": t, "name": MITRE_NAMES.get(t, "")} for t in techniques
                ]
            }
    return out


def enrich(report: dict, fetch_cves: bool = True, max_cves: int = 15) -> dict:
    """
    Build the enrichment payload for a snapshot.

    Failures degrade rather than raise: a report without CVE detail is still a
    report, and an NVD outage should not stop an analysis.
    """
    enrichment: dict = {"cves": {}, "mitre": {}, "errors": []}

    try:
        enrichment["mitre"] = map_findings_to_mitre(report)
    except Exception as exc:  # noqa: BLE001
        enrichment["errors"].append(f"mitre mapping: {exc}")

    if fetch_cves:
        delay = NVD_DELAY_AUTH if os.environ.get("NVD_API_KEY") else NVD_DELAY_UNAUTH
        ids = extract_cve_ids(report, limit=max_cves)
        for i, cve_id in enumerate(ids):
            record = fetch_cve(cve_id)
            if record:
                enrichment["cves"][cve_id] = record
            if i < len(ids) - 1:
                time.sleep(delay)
        if ids and not enrichment["cves"]:
            enrichment["errors"].append(
                "No CVE detail could be retrieved from the NVD"
            )

    return enrichment
