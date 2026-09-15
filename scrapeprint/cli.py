import asyncio
import secrets
from pathlib import Path
from typing import Annotated

import typer

from scrapeprint.models import Engine, RunResult, Scenario
from scrapeprint.runner import Settings, benchmark
from scrapeprint.storage import read_results
from scrapeprint.summary import summarize as markdown_summary

app = typer.Typer(no_args_is_help=True, help="Benchmark browsers on web-scraping.dev only.")


def selection(value: str, enum_type: type, allow_all: bool = False) -> list:
    if value.strip() == "all" and allow_all:
        return list(enum_type)
    try:
        selected = [enum_type(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise typer.BadParameter(f"Choose from: {', '.join(e.value for e in enum_type)}") from exc
    if len(selected) != len(set(selected)):
        raise typer.BadParameter("Duplicate selections are not allowed")
    return selected


def progress(result: RunResult) -> None:
    label = "warmup" if result.warmup else "measured"
    status = "PASS" if result.success else "FAIL"
    typer.echo(
        f"{status} {result.engine}/{result.scenario} {label} #{result.run_number}: "
        f"{result.extracted_record_count} records, {result.total_time_s:.3f}s"
    )
    if result.error_message:
        typer.echo(f"  {result.error_type}: {result.error_message}")


@app.command()
def run(
    engines: str = "chromium,obscura",
    scenarios: str = "all",
    runs: Annotated[int, typer.Option(min=1)] = 5,
    results_dir: Path = Path("results"),
    timeout: Annotated[float, typer.Option(min=1, help="Per-action timeout in seconds.")] = 120,
    run_timeout: Annotated[float, typer.Option(min=1, help="Whole-run timeout in seconds.")] = 900,
    delay: Annotated[
        float, typer.Option(min=2, help="Minimum delay between allowed requests.")
    ] = 2,
    seed: Annotated[int | None, typer.Option(help="Reproduce randomized engine ordering.")] = None,
) -> None:
    selected_engines = selection(engines, Engine)
    selected_scenarios = selection(scenarios, Scenario, allow_all=True)
    settings = Settings(
        timeout_ms=int(timeout * 1000),
        run_timeout_s=run_timeout,
        delay_s=delay,
        seed=seed if seed is not None else secrets.randbits(32),
    )
    typer.echo(f"Sequential benchmark; order seed={settings.seed}; one warmup per engine/scenario.")
    try:
        results = asyncio.run(
            benchmark(selected_engines, selected_scenarios, runs, results_dir, settings, progress)
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(markdown_summary(results))
    if any(not r.success for r in results):
        raise typer.Exit(1)


@app.command()
def summarize(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Print a correctness, latency and memory comparison from JSONL."""
    try:
        typer.echo(markdown_summary(read_results(path)))
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


if __name__ == "__main__":
    app()
