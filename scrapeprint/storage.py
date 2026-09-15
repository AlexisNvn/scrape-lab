import json
import os
from pathlib import Path

from scrapeprint.models import RunResult


def append_result(path: Path, result: RunResult) -> None:
    """Durably append each completed attempt; callers execute sequentially."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(result.model_dump_json() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_extraction(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of earlier runs.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(records, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def next_run_number(root: Path) -> int:
    numbers = [int(p.stem) for p in (root / "extractions").glob("*/*/*.json") if p.stem.isdigit()]
    path = root / "runs.jsonl"
    if path.exists():
        numbers.extend(r.run_number for r in read_results(path))
    return max(numbers, default=0) + 1


def read_results(path: Path) -> list[RunResult]:
    results = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                results.append(RunResult.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: invalid result: {exc}") from exc
    return results
