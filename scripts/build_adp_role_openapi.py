from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "api" / "rideresolve-tools.openapi.json"
OUTPUT_DIRECTORY = ROOT / "api" / "adp"

ROLE_CONFIG = {
    "evidence": {
        "title": "RideResolve Evidence Tools",
        "description": "Read-only, run-scoped tools for the Evidence Collection role.",
        "paths": (
            "/tools/get_case_snapshot",
            "/tools/get_trip_evidence",
            "/tools/get_policy_rules",
        ),
    },
    "rider": {
        "title": "RideResolve Rider Tools",
        "description": "Read-only, run-scoped evidence tool for the Rider Advocate role.",
        "paths": ("/tools/get_trip_evidence",),
    },
    "driver": {
        "title": "RideResolve Driver Tools",
        "description": "Read-only, run-scoped evidence tool for the Driver Advocate role.",
        "paths": ("/tools/get_trip_evidence",),
    },
    "policy": {
        "title": "RideResolve Policy Tools",
        "description": "Read-only, run-scoped policy and precedent tools for the Policy & Precedent role.",
        "paths": (
            "/tools/get_policy_rules",
            "/tools/search_precedents",
        ),
    },
    "gate": {
        "title": "RideResolve Deterministic Gate Tools",
        "description": (
            "Workflow-owned deterministic evaluation and final validation tools. "
            "Do not attach this connector to the Judge Agent."
        ),
        "paths": (
            "/tools/get_deterministic_evaluation",
            "/tools/validate_recommendation",
        ),
    },
}


def build_role_documents(master: dict) -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for role, config in ROLE_CONFIG.items():
        document = copy.deepcopy(master)
        document["info"]["title"] = config["title"]
        document["info"]["description"] = config["description"]
        document["paths"] = {
            path: copy.deepcopy(master["paths"][path]) for path in config["paths"]
        }
        documents[role] = document
    return documents


def main() -> None:
    master = json.loads(SOURCE.read_text(encoding="utf-8"))
    documents = build_role_documents(master)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for role, document in documents.items():
        output = OUTPUT_DIRECTORY / f"rideresolve-{role}-tools.openapi.json"
        output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output)


if __name__ == "__main__":
    main()
