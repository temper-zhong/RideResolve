from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

ROOT_FILES = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "README.md",
    "app.py",
    "container_entrypoint.py",
    "pyproject.toml",
    "requirements.lock",
}

DIRECTORY_SUFFIXES = {
    ".github": {".yml", ".yaml"},
    "api": {".json", ".md"},
    "data/cases": {".json"},
    "data/feedback": {".json"},
    "data/official_sources": {".json", ".md"},
    "data/policies": {".json"},
    "docs/adp": {".json", ".md", ".py"},
    "docs/assets": {".md", ".png", ".jpg", ".jpeg"},
    "docs/process_records/submission": {".md", ".json", ".png", ".jpg", ".jpeg", ".mp4", ".webm"},
    "integrations": {".py", ".json", ".md"},
    "rideresolve": {".py"},
    "scripts": {".cjs", ".py"},
    "tests": {".py"},
}

DOC_FILES = {
    "docs/ARCHITECTURE.md",
    "docs/DEMO_WALKTHROUGH.md",
    "docs/GATE_STATUS.md",
    "docs/LEGACY_ASSETS.md",
    "docs/OFFICIAL_DATASET_INTEGRATION.md",
    "docs/PUBLIC_DEMO_CASES.md",
    "docs/SUBMISSION_CHECKLIST.md",
    "docs/SUBMISSION_COPY.md",
    "docs/V0_6_LOCAL_HANDOFF.md",
    "docs/WORKBUDDY_INTEGRATION.md",
    "docs/process_records/README.md",
    "docs/streamlit-demo-preview.png",
}

TEXT_SUFFIXES = {
    ".dockerignore",
    ".example",
    ".gitignore",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

BLOCKED_CONTENT = {
    "local Windows user path": re.compile(rb"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+"),
    "private key material": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "JWT-like bearer token": re.compile(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"),
    "Tencent-style secret id": re.compile(rb"AKID[A-Za-z0-9]{20,}"),
}


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _files_under(relative_directory: str, suffixes: set[str]) -> list[Path]:
    directory = ROOT / relative_directory
    if not directory.is_dir():
        return []
    return [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and "__pycache__" not in path.parts
    ]


def submission_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(ROOT / name for name in DOC_FILES)
    for relative_directory, suffixes in DIRECTORY_SUFFIXES.items():
        files.extend(_files_under(relative_directory, suffixes))
    unique = sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())
    missing = [path.relative_to(ROOT).as_posix() for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Submission source files are missing: {missing}")
    return unique


def scan_submission_files(files: list[Path]) -> None:
    violations: list[str] = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        for label, pattern in BLOCKED_CONTENT.items():
            if pattern.search(data):
                violations.append(f"{path.relative_to(ROOT).as_posix()}: {label}")
    if violations:
        raise ValueError("Submission privacy/secret scan failed:\n" + "\n".join(violations))


def _submission_media() -> list[Path]:
    evidence_dir = ROOT / "docs" / "process_records" / "submission"
    media_suffixes = {".png", ".jpg", ".jpeg", ".mp4", ".webm"}
    return sorted(
        (path for path in evidence_dir.glob("*") if path.suffix.lower() in media_suffixes),
        key=lambda path: path.name,
    )


def verify_final_eligibility() -> None:
    media = _submission_media()
    image_count = sum(path.suffix.lower() in {".png", ".jpg", ".jpeg"} for path in media)
    video_count = sum(path.suffix.lower() in {".mp4", ".webm"} for path in media)
    if image_count < 3 and video_count < 1:
        raise ValueError(
            "Final package blocked: add at least three manually reviewed CodeBuddy/WorkBuddy "
            "screenshots or one qualifying recording under docs/process_records/submission/."
        )

    review_path = ROOT / "docs" / "process_records" / "submission" / "privacy_review.json"
    if not review_path.is_file():
        raise ValueError("Final package blocked: privacy_review.json is missing.")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("approved") is not True:
        raise ValueError("Final package blocked: privacy_review.json must set approved to true.")
    reviewed_files = review.get("files")
    expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest().upper() for path in media}
    if reviewed_files != expected:
        raise ValueError(
            "Final package blocked: privacy_review.json file hashes do not match the evidence media."
        )


def build_package(output: Path, *, final: bool) -> tuple[int, str]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {output}")
    if final:
        verify_final_eligibility()

    files = submission_files()
    scan_submission_files(files)
    inventory = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    manifest = {
        "schema_version": 1,
        "project": "RideResolve",
        "project_version": project_version(),
        "package_kind": "FINAL" if final else "CANDIDATE_NOT_FOR_SUBMISSION",
        "canonical_architecture": "NATURAL_LANGUAGE_INTAKE_SERIAL_FIVE_AGENT_DETERMINISTIC_GATE",
        "public_input": "SYS.UserQuery",
        "internal_only_fields": ["run_id", "run_context"],
        "data_precedence": "OFFICIAL_OVER_LEGACY_MOCK",
        "excluded": [
            "dist/ and prior ZIP artifacts",
            "var/ and all local credentials",
            "RideResolve-Orchestration-import.zip legacy snapshot",
            "full process transcript exports",
            "unreviewed ADP, audit, trace, container, and pod screenshots",
        ],
        "files": inventory,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive_name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(archive_name, date_time=FIXED_ZIP_TIME)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("SUBMISSION_MANIFEST.json", date_time=FIXED_ZIP_TIME)
        info.create_system = 3
        info.external_attr = (0o100644 & 0xFFFF) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, manifest_bytes)

    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return len(files) + 1, digest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a curated, privacy-scanned RideResolve submission package"
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Require complete, hash-reviewed CodeBuddy/WorkBuddy eligibility evidence",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    count, digest = build_package(output, final=args.final)
    print(f"package={output}")
    print(f"kind={'FINAL' if args.final else 'CANDIDATE_NOT_FOR_SUBMISSION'}")
    print(f"entries={count}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
