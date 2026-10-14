"""Executa Bandit e exige revisão explícita para qualquer achado novo/alterado."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "security" / "bandit-reviewed.json"
REPORT = ROOT / "test-results" / "bandit.json"


def fingerprint(finding):
    path = Path(finding["filename"])
    if not path.is_absolute():
        path = ROOT / path
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "test_id": finding["test_id"],
        "severity": finding["issue_severity"],
        "confidence": finding["issue_confidence"],
        "line": finding["line_number"],
    }


def main():
    REPORT.parent.mkdir(exist_ok=True)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            "python/app",
            "-f",
            "json",
            "-o",
            str(REPORT),
            "-q",
        ],
        cwd=ROOT,
        check=False,
    )
    if run.returncode not in (0, 1) or not REPORT.exists():
        raise SystemExit("Bandit não concluiu; revisão estática indisponível.")
    report = json.loads(REPORT.read_text())
    if report.get("errors"):
        raise SystemExit("Bandit encontrou arquivos que não pôde analisar.")
    reviewed = json.loads(REVIEW.read_text())["reviewed"]
    unexpected = []
    for item in report["results"]:
        current = fingerprint(item)
        accepted = any(
            all(entry.get(k) == v for k, v in current.items()) and entry.get("reason")
            for entry in reviewed
        )
        if item["issue_severity"] == "HIGH" or not accepted:
            unexpected.append(current)
    print(
        f"Bandit: {len(report['results'])} alertas, {len(unexpected)} sem revisão válida. Relatório: test-results/bandit.json"
    )
    for item in unexpected:
        print(
            f"Revisar {item['file']}:{item['line']} {item['test_id']} {item['severity']}"
        )
    if unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
