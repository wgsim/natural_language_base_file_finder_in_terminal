#!/usr/bin/env python3
"""Fail CI only when pip-audit findings are high/critical severity."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

SEVERITY_ORDER = {"unknown": 0, "low": 1, "medium": 2, "moderate": 2, "high": 3, "critical": 4}

# CVSS v3+ numeric thresholds
CVSS_CRITICAL = 9.0
CVSS_HIGH = 7.0
CVSS_MEDIUM = 4.0
CVSS_LOW = 0.1


@dataclass
class Finding:
    package: str
    version: str
    vuln_id: str
    severity: str
    source_id: str


def _severity_from_score(score: str) -> str:
    try:
        value = float(score.strip())
    except ValueError:
        return "unknown"

    if value >= CVSS_CRITICAL:
        return "critical"
    if value >= CVSS_HIGH:
        return "high"
    if value >= CVSS_MEDIUM:
        return "medium"
    if value >= CVSS_LOW:
        return "low"
    return "unknown"


def _pick_higher_severity(lhs: str, rhs: str) -> str:
    return lhs if SEVERITY_ORDER[lhs] >= SEVERITY_ORDER[rhs] else rhs


def _fetch_osv_record(vuln_id: str, timeout: float) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(vuln_id, safe="")
    url = f"https://api.osv.dev/v1/vulns/{encoded}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _extract_record_severity(record: dict[str, Any]) -> str:
    severity = "unknown"

    database_specific = record.get("database_specific")
    if isinstance(database_specific, dict):
        db_severity = database_specific.get("severity")
        if isinstance(db_severity, str):
            normalized = db_severity.strip().lower()
            if normalized in SEVERITY_ORDER:
                severity = _pick_higher_severity(severity, normalized)

    ecosystem_specific = record.get("ecosystem_specific")
    if isinstance(ecosystem_specific, dict):
        eco_severity = ecosystem_specific.get("severity")
        if isinstance(eco_severity, str):
            normalized = eco_severity.strip().lower()
            if normalized in SEVERITY_ORDER:
                severity = _pick_higher_severity(severity, normalized)

    score_entries = record.get("severity")
    if isinstance(score_entries, list):
        for entry in score_entries:
            if not isinstance(entry, dict):
                continue
            score = entry.get("score")
            if isinstance(score, str):
                severity = _pick_higher_severity(severity, _severity_from_score(score))

    return severity


def _load_findings(path: str, timeout: float) -> list[Finding]:
    with open(path, encoding="utf-8") as f:
        report = json.load(f)

    dependencies = report.get("dependencies")
    if not isinstance(dependencies, list):
        return []

    findings: list[Finding] = []
    for dep in dependencies:
        if not isinstance(dep, dict):
            continue

        package = str(dep.get("name", "unknown"))
        version = str(dep.get("version", "unknown"))
        vulns = dep.get("vulns")
        if not isinstance(vulns, list):
            continue

        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue

            vuln_id = str(vuln.get("id", "unknown"))
            aliases = vuln.get("aliases")
            alias_ids = [str(vuln_id)]
            if isinstance(aliases, list):
                alias_ids.extend(str(alias) for alias in aliases)

            best_severity = "unknown"
            best_source_id = vuln_id
            for candidate_id in alias_ids:
                record = _fetch_osv_record(candidate_id, timeout=timeout)
                if record is None:
                    continue
                candidate_severity = _extract_record_severity(record)
                if SEVERITY_ORDER[candidate_severity] > SEVERITY_ORDER[best_severity]:
                    best_severity = candidate_severity
                    best_source_id = candidate_id

            findings.append(
                Finding(
                    package=package,
                    version=version,
                    vuln_id=vuln_id,
                    severity=best_severity,
                    source_id=best_source_id,
                )
            )

    return findings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="pip-audit.json", help="Path to pip-audit JSON output")
    parser.add_argument(
        "--min-severity",
        choices=("high", "critical"),
        default="high",
        help="Minimum severity level that fails CI",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="HTTP timeout in seconds for OSV severity lookups",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    min_level = SEVERITY_ORDER[args.min_severity]

    findings = _load_findings(args.input, timeout=args.timeout)
    if not findings:
        print("pip-audit severity gate: no vulnerabilities found")
        return 0

    fail_findings = [f for f in findings if SEVERITY_ORDER[f.severity] >= min_level]

    print("pip-audit severity gate summary:")
    for finding in findings:
        print(
            f"- {finding.package}=={finding.version}: {finding.vuln_id} "
            f"(severity={finding.severity}, source={finding.source_id})"
        )

    if fail_findings:
        print(
            f"pip-audit severity gate failed: found {len(fail_findings)} "
            f"{args.min_severity}+ vulnerabilities",
            file=sys.stderr,
        )
        return 1

    print(f"pip-audit severity gate passed: no {args.min_severity}+ vulnerabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
