from __future__ import annotations

import argparse
import json
from pathlib import Path

from rideresolve.session_openapi import (
    build_intake_openapi_schema,
    build_session_role_documents,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = ROOT / "api" / "adp" / "v0_6"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ADP OpenAPI files for session mode")
    parser.add_argument("--server-url", required=True)
    args = parser.parse_args()
    documents = {
        "intake": build_intake_openapi_schema(args.server_url),
        **build_session_role_documents(args.server_url),
    }
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

