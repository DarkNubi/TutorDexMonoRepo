#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    "AGENTS.md",
    "docs/README.md",
    "docs/SYSTEM_MAP.md",
    "docs/ARCHITECTURE.md",
    "docs/KNOWN_INVARIANTS.md",
    "docs/DEPLOYMENT_TOPOLOGY.md",
    "docs/OPERATIONS.md",
    "docs/TESTING.md",
    "docs/SYSTEM_INTERNAL.md",
    "docs/DOCS_CHANGE_POLICY.md",
    "docs/DOCS_CATALOG.md",
    "docs/DOCS_SCORECARD.md",
    "docs/GENERATED_INVENTORY.md",
    "docs/adr/README.md",
    "docs/adr/ADR_TEMPLATE.md",
]

METADATA_REQUIRED = [
    "AGENTS.md",
    "TutorDexAggregator/AGENTS.md",
    "docs/README.md",
    "docs/SYSTEM_MAP.md",
    "docs/ARCHITECTURE.md",
    "docs/KNOWN_INVARIANTS.md",
    "docs/DEPLOYMENT_TOPOLOGY.md",
    "docs/OPERATIONS.md",
    "docs/TESTING.md",
    "docs/DOCS_CHANGE_POLICY.md",
    "docs/DOCS_CATALOG.md",
    "docs/DOCS_SCORECARD.md",
    "docs/GENERATED_INVENTORY.md",
    "docs/adr/README.md",
    "docs/adr/ADR_TEMPLATE.md",
]

REQUIRED_POINTERS = {
    "AGENTS.md": [
        "docs/DOCS_CHANGE_POLICY.md",
        "docs/adr/README.md",
        "python3 scripts/docs_health.py",
        "TutorDexAggregator/AGENTS.md",
    ],
    "TutorDexAggregator/AGENTS.md": [
        "docs/SYSTEM_MAP.md",
        "python3 scripts/docs_health.py",
    ],
    "docs/README.md": [
        "DOCS_CHANGE_POLICY.md",
        "DOCS_CATALOG.md",
        "DOCS_SCORECARD.md",
        "GENERATED_INVENTORY.md",
        "adr/README.md",
    ],
    "docs/SYSTEM_MAP.md": [
        "GENERATED_INVENTORY.md",
        "docs_health.py",
    ],
    "docs/TESTING.md": [
        "python3 scripts/docs_health.py",
        "docs_change_guard.py",
    ],
}

FORBIDDEN_PROOF_WORDS = [
    "production is healthy",
    "prod is healthy",
    "verified prod",
    "verified production",
]


def read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def has_metadata(text: str) -> bool:
    required = [
        "**Docs metadata:**",
        "**Status:**",
        "**Owner:**",
        "**Last reviewed:**",
        "**Review trigger:**",
    ]
    return all(token in text for token in required)


def check_with_reader(reader) -> list[str]:
    findings: list[str] = []

    for rel in REQUIRED_DOCS:
        if not reader(rel):
            findings.append(f"missing required doc: {rel}")

    for rel in METADATA_REQUIRED:
        text = reader(rel)
        if text and not has_metadata(text):
            findings.append(f"missing docs metadata block: {rel}")

    for rel, pointers in REQUIRED_POINTERS.items():
        text = reader(rel)
        if not text:
            continue
        for pointer in pointers:
            if pointer not in text:
                findings.append(f"missing pointer {pointer!r} in {rel}")

    for rel in REQUIRED_DOCS:
        text = reader(rel).lower()
        for word in FORBIDDEN_PROOF_WORDS:
            if word in text:
                findings.append(f"overconfident proof wording {word!r} in {rel}")

    adr_index = reader("docs/adr/README.md")
    if "ADR-0001" not in adr_index:
        findings.append("ADR index does not link historical ADR-0001")

    return findings


def check() -> list[str]:
    return check_with_reader(read)


def self_test() -> list[str]:
    good = {rel: "ok" for rel in REQUIRED_DOCS}
    for rel in METADATA_REQUIRED:
        good[rel] = (
            "**Docs metadata:**\n"
            "**Status:** active\n"
            "**Owner:** Mochi\n"
            "**Last reviewed:** 2026-06-17\n"
            "**Review trigger:** test\n"
        )
    for rel, pointers in REQUIRED_POINTERS.items():
        good[rel] = good.get(rel, "") + "\n" + "\n".join(pointers)
    good["docs/adr/README.md"] = good["docs/adr/README.md"] + "\nADR-0001\n"

    cases = {
        "missing doc": ({k: v for k, v in good.items() if k != "docs/TESTING.md"}, "missing required doc: docs/TESTING.md"),
        "missing metadata": ({**good, "docs/TESTING.md": "no metadata"}, "missing docs metadata block: docs/TESTING.md"),
        "missing pointer": ({**good, "AGENTS.md": "no pointer"}, "missing pointer"),
        "forbidden wording": ({**good, "docs/OPERATIONS.md": good["docs/OPERATIONS.md"] + "\nproduction is healthy\n"}, "overconfident proof wording"),
        "missing adr link": ({**good, "docs/adr/README.md": good["docs/adr/README.md"].replace("ADR-0001", "")}, "ADR index does not link historical ADR-0001"),
    }
    failures: list[str] = []
    if check_with_reader(lambda rel: good.get(rel, "")):
        failures.append("good fixture produced findings")
    for name, (fixture, expected) in cases.items():
        findings = check_with_reader(lambda rel, fixture=fixture: fixture.get(rel, ""))
        if not any(expected in finding for finding in findings):
            failures.append(f"{name} did not include expected finding {expected!r}: {findings}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="TutorDex docs health smoke.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("self-test: FAIL")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print("self-test: PASS")
        return 0
    findings = check()
    if findings:
        if not args.quiet:
            print("TutorDex docs health: FAIL")
            for finding in findings:
                print(f"- {finding}")
        return 1
    if not args.quiet:
        print("TutorDex docs health: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
