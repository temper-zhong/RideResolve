from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.build_submission_package import build_package


def test_candidate_package_is_curated_and_declares_intake(tmp_path: Path) -> None:
    output = tmp_path / "submission.zip"

    count, digest = build_package(output, final=False)

    assert count > 1
    assert len(digest) == 64
    assert output.with_suffix(".zip.sha256").is_file()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "api/rideresolve-tools.openapi.json" in names
        assert "api/adp/README.md" in names
        assert "api/adp/v0_6/rideresolve-intake-tools.openapi.json" in names
        assert "docs/adp/accuracy_first_manifest.json" in names
        assert "rideresolve/intake.py" in names
        assert "RideResolve-Orchestration-import.zip" not in names
        assert not any(name.startswith("dist/") for name in names)
        assert not any(name.startswith("var/") for name in names)
        assert not any(name.endswith(".redacted.txt") for name in names)
        manifest = json.loads(archive.read("SUBMISSION_MANIFEST.json"))
        assert manifest["package_kind"] == "CANDIDATE_NOT_FOR_SUBMISSION"
        assert manifest["public_input"] == "SYS.UserQuery"
        assert manifest["internal_only_fields"] == ["run_id", "run_context"]
        assert manifest["data_precedence"] == "OFFICIAL_OVER_LEGACY_MOCK"
