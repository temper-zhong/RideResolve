"""Read-only ADP trace timeline analyser.

Why this exists
---------------
The ADP console reports a per-node figure for each Agent, and the tool panel
reports a duration for each tool span. Those two sets of numbers do not add up
to the run's total. On the 2026-10-12 baseline run (164.3s) they explained
60.9s; on the pass-1 run (178.5s) they explained 58.7s. Roughly two thirds of
every run is attributed to nothing at all.

The ADP export already carries absolute start and end timestamps for every
model call and every tool call (see `AdpTrace` in `rideresolve/probe_validation.py`).
That is enough to subtract the union of all instrumented intervals from the
workflow span. Whatever remains is time no console figure claims: node-to-node
hand-off, queueing, serialisation, gateway round trips and retries.

This script only reads. It changes no artifact and is not part of the pipeline.

Usage
-----
    python scripts/analyze_trace_timeline.py path/to/adp_trace_export.json
    python scripts/analyze_trace_timeline.py path/to/export.json --top 12

The export must validate as `AdpTrace`, i.e. it must be the preserved ADP
export with `workflow_started_at`, `workflow_ended_at`, `model_calls` and
`tool_calls`. Reconstructed traces are rejected on purpose.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rideresolve.probe_validation import AdpTrace, load_adp_trace_artifact  # noqa: E402


@dataclass(frozen=True)
class Interval:
    kind: str
    label: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def collect_intervals(trace: AdpTrace) -> list[Interval]:
    origin = trace.workflow_started_at
    items: list[Interval] = []

    for call in trace.model_calls:
        items.append(
            Interval(
                kind="MODEL",
                label=f"{call.role.value}/{call.call_id}",
                start=(call.started_at - origin).total_seconds(),
                end=(call.ended_at - origin).total_seconds(),
            )
        )

    for call in trace.tool_calls:
        items.append(
            Interval(
                kind="TOOL",
                label=f"{call.role.value}/{call.operation_id}/{call.request_id[:14]}",
                start=(call.started_at - origin).total_seconds(),
                end=(call.ended_at - origin).total_seconds(),
            )
        )

    items.sort(key=lambda item: (item.start, item.end))
    return items


def union_length(intervals: list[Interval]) -> float:
    """Wall-clock length covered by at least one interval."""
    total = 0.0
    current_start: float | None = None
    current_end = 0.0

    for item in sorted(intervals, key=lambda entry: (entry.start, entry.end)):
        if current_start is None:
            current_start, current_end = item.start, item.end
        elif item.start <= current_end:
            current_end = max(current_end, item.end)
        else:
            total += current_end - current_start
            current_start, current_end = item.start, item.end

    if current_start is not None:
        total += current_end - current_start
    return total


def naive_sum(intervals: list[Interval]) -> float:
    return sum(item.duration for item in intervals)


def overlap_seconds(model: list[Interval], tool: list[Interval]) -> float:
    """How much MODEL time is also covered by TOOL time.

    A non-zero result means the console's node figure and its tool panel figure
    are double-counting the same wall-clock, so they must not be added together.
    """
    overlap = 0.0
    for m in model:
        for t in tool:
            lo = max(m.start, t.start)
            hi = min(m.end, t.end)
            if hi > lo:
                overlap += hi - lo
    return overlap


def gaps(intervals: list[Interval], span_end: float) -> list[tuple[float, float, str]]:
    """Uncovered windows, each labelled with whatever follows it."""
    found: list[tuple[float, float, str]] = []
    cursor = 0.0

    for item in intervals:
        if item.start > cursor + 1e-9:
            found.append((cursor, item.start, f"before {item.kind} {item.label}"))
        cursor = max(cursor, item.end)

    if span_end > cursor + 1e-9:
        found.append((cursor, span_end, "after last instrumented span"))

    found.sort(key=lambda entry: entry[1] - entry[0], reverse=True)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="path to the preserved ADP trace export")
    parser.add_argument("--top", type=int, default=10, help="how many gaps to list")
    args = parser.parse_args()

    artifact = load_adp_trace_artifact(args.trace)
    trace = artifact.trace

    span = (trace.workflow_ended_at - trace.workflow_started_at).total_seconds()
    items = collect_intervals(trace)
    model = [item for item in items if item.kind == "MODEL"]
    tool = [item for item in items if item.kind == "TOOL"]

    covered = union_length(items)
    uncovered = span - covered
    overlap = overlap_seconds(model, tool)

    print(f"trace          : {args.trace}")
    print(f"run_id         : {trace.run_id}")
    print(f"platform trace : {trace.platform_trace_id}")
    print(f"model calls    : {len(model)}")
    print(f"tool calls     : {len(tool)}")
    print()
    print(f"workflow span  : {span:10.3f}s")
    print(f"naive sum      : {naive_sum(items):10.3f}s   (model + tool, added blindly)")
    print(f"union covered  : {covered:10.3f}s   (what actually happened on the clock)")
    print(f"UNATTRIBUTED   : {uncovered:10.3f}s   ({uncovered / span * 100:.1f}% of the run)")
    if overlap > 1e-9:
        print()
        print(f"NOTE: MODEL and TOOL intervals overlap by {overlap:.3f}s.")
        print("      The console's node figure and tool panel figure are therefore")
        print("      not additive. Do not sum them.")

    print()
    print("timeline")
    print(f"  {'start':>9} {'end':>9} {'dur':>9}  {'gap':>9}  entry")
    print(f"  {'-' * 9} {'-' * 9} {'-' * 9}  {'-' * 9}  {'-' * 46}")
    cursor = 0.0
    for item in items:
        gap = item.start - cursor
        print(
            f"  {item.start:9.3f} {item.end:9.3f} {item.duration:9.3f}  "
            f"{gap:9.3f}  {item.kind:5} {item.label}"
        )
        cursor = max(cursor, item.end)

    print()
    print(f"largest uncovered windows (top {args.top})")
    for start, end, label in gaps(items, span)[: args.top]:
        print(f"  {end - start:8.3f}s   t={start:8.3f} -> {end:8.3f}   {label}")

    print()
    print("per-role instrumented time (union, not sum)")
    for role in sorted({item.label.split("/")[0] for item in items}):
        role_items = [item for item in items if item.label.startswith(f"{role}/")]
        print(f"  {role:20} {union_length(role_items):8.3f}s  over {len(role_items)} span(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
