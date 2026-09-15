import math
from collections import defaultdict
from statistics import median

from scrapeprint.models import RunResult


def percentile95(values: list[float]) -> float:
    """Nearest-rank percentile, including well-defined n=1 behavior."""
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def summarize(results: list[RunResult]) -> str:
    groups = defaultdict(list)
    for result in results:
        if not result.warmup:
            groups[result.engine.value, result.scenario.value].append(result)
    lines = [
        "| Engine | Scenario | Successful runs | Success rate | Median total (s) | "
        "p95 total (s) | Median peak memory (MiB) | Median extracted records |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (engine, scenario), runs in sorted(groups.items()):
        good = [r for r in runs if r.success]
        values = [r.total_time_s for r in good]
        metrics = (
            (
                f"{median(values):.3f} | {percentile95(values):.3f} | "
                f"{median(r.peak_memory_bytes for r in good) / 2**20:.2f} | "
                f"{median(r.extracted_record_count for r in good):g}"
            )
            if good
            else "— | — | — | —"
        )
        lines.append(
            f"| {engine} | {scenario} | {len(good)}/{len(runs)} | "
            f"{len(good) / len(runs):.1%} | {metrics} |"
        )
    lines.append(
        "\nWarmups excluded. Time, memory and record medians use successful runs only; "
        "p95 uses nearest rank. Failed runs remain in the success-rate denominator."
    )
    return "\n".join(lines)
