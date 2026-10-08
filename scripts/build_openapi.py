from __future__ import annotations

import json
import argparse
from pathlib import Path

from rideresolve.openapi_schema import build_openapi_schema


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "api" / "rideresolve-tools.openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fixed HTTPS OpenAPI document for ADP")
    parser.add_argument("--server-url", required=True, help="Explicit deployed HTTPS base URL")
    args = parser.parse_args()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(build_openapi_schema(args.server_url), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
