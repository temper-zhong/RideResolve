from __future__ import annotations

import argparse
import hashlib
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def runtime_files() -> list[Path]:
    files = [
        ROOT / "api" / "rideresolve-tools.openapi.json",
        ROOT / "container_entrypoint.py",
        ROOT / "Dockerfile",
        ROOT / "pyproject.toml",
        ROOT / "README.md",
    ]
    for relative_directory, pattern in (
        ("api/adp/v0_6", "*.json"),
        ("data/cases", "*.json"),
        ("data/feedback", "*.json"),
        ("data/policies", "*.json"),
        ("rideresolve", "*.py"),
    ):
        files.extend(sorted((ROOT / relative_directory).glob(pattern)))
    return files


def build_package(output: Path) -> tuple[int, str]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    files = runtime_files()
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing runtime files: {missing}")

    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive_name = path.relative_to(ROOT).as_posix()
            if not archive_name.isascii() or "\\" in archive_name:
                raise ValueError(f"CloudBase package entry is not portable: {archive_name}")
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
            info = zipfile.ZipInfo(
                archive_name,
                date_time=(
                    max(modified.year, 1980),
                    modified.month,
                    modified.day,
                    modified.hour,
                    modified.minute,
                    modified.second,
                ),
            )
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())

    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    return len(files), digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a portable CloudBase source ZIP")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    count, digest = build_package(output)
    print(f"package={output}")
    print(f"entries={count}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
