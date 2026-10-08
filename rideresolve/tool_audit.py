from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any


class JsonlAuditLogger:
    """Append-only structured audit log. Callers must not pass raw credentials."""

    def __init__(self, path: Path, *, emit_stdout: bool = False) -> None:
        self.path = path
        self.emit_stdout = emit_stdout
        self._lock = threading.Lock()

    def append(self, event: dict[str, Any]) -> None:
        serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
            if self.emit_stdout:
                print(f"RIDEREsolve_AUDIT {serialized}", file=sys.stdout, flush=True)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
