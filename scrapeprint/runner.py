import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from playwright.async_api import async_playwright

from scrapeprint.adapters import ADAPTERS
from scrapeprint.metrics import ProcessMonitor
from scrapeprint.models import Engine, Extraction, RunResult, Scenario
from scrapeprint.policy import USER_AGENT, SitePolicy
from scrapeprint.scenarios import SCENARIOS
from scrapeprint.scenarios.base import ExtractionError, ScenarioContext
from scrapeprint.storage import append_result, next_run_number, write_extraction
from scrapeprint.validation import validate


@dataclass(frozen=True)
class Settings:
    timeout_ms: int = 120_000
    run_timeout_s: float = 900
    delay_s: float = 2.0
    viewport_width: int = 1280
    viewport_height: int = 720
    locale: str = "en-US"
    user_agent: str = USER_AGENT
    seed: int = 0


async def run_one(
    engine: Engine,
    scenario: Scenario,
    run_number: int,
    warmup: bool,
    root: Path,
    session_id: str,
    settings: Settings,
    policy: SitePolicy,
    preflight_error: Exception | None = None,
) -> RunResult:
    result = RunResult(
        session_id=session_id,
        engine=engine,
        scenario=scenario,
        run_number=run_number,
        warmup=warmup,
        settings={**asdict(settings), "effective_delay_s": policy.delay},
    )
    adapter = ADAPTERS[engine]()
    monitor = ProcessMonitor()
    playwright = None
    ctx = None
    extraction = Extraction()
    policy.failures.clear()
    cancelled = None
    phase = "startup"
    started = phase_started = time.perf_counter()
    monitor.start()
    try:
        async with asyncio.timeout(settings.run_timeout_s):
            if preflight_error:
                raise preflight_error
            playwright = await async_playwright().start()
            browser = await adapter.start(playwright, settings.timeout_ms)
            result.engine_version = browser.version
            context = await browser.new_context(
                viewport={"width": settings.viewport_width, "height": settings.viewport_height},
                user_agent=settings.user_agent,
                locale=settings.locale,
                service_workers="block",
                accept_downloads=False,
            )
            # New non-persistent context guarantees empty cookies, local/session storage,
            # IndexedDB and cache without navigating or altering application state.
            await context.clear_cookies()
            context.set_default_timeout(settings.timeout_ms)
            context.set_default_navigation_timeout(settings.timeout_ms)
            await context.route("**/*", policy.route)
            page = await context.new_page()
            ctx = ScenarioContext(page=page, policy=policy, extraction=extraction)
            result.startup_time_s = time.perf_counter() - phase_started
            phase = "scenario"
            phase_started = time.perf_counter()
            await SCENARIOS[scenario](ctx)
            if policy.failures:
                raise ExtractionError("; ".join(policy.failures))
            report = validate(extraction, scenario)
            if not report.valid:
                raise ExtractionError("Extraction validation failed: " + report.model_dump_json())
            result.success = True
    except asyncio.CancelledError as exc:
        cancelled = exc
        result.error_type = "CancelledError"
        result.error_message = "Run interrupted; partial extraction preserved"
    except Exception as exc:
        result.error_type = type(exc).__name__
        result.error_message = str(exc) or (
            f"{type(exc).__name__} during {phase}; "
            f"whole-run limit={settings.run_timeout_s}s, action limit={settings.timeout_ms}ms"
        )
    finally:
        elapsed = time.perf_counter() - phase_started
        if phase == "startup":
            result.startup_time_s = elapsed
        else:
            result.navigation_time_s = ctx.navigation_time_s
            result.extraction_time_s = max(0, elapsed - ctx.navigation_time_s)
        # Independent cleanup actions still run if any earlier close operation fails.
        for cleanup in (adapter.close,):
            try:
                await cleanup()
            except Exception as exc:
                result.success = False
                result.error_type = result.error_type or type(exc).__name__
                result.error_message = (result.error_message or "") + f"; cleanup: {exc}"
        if playwright:
            try:
                async with asyncio.timeout(10):
                    await playwright.stop()
            except Exception as exc:
                result.success = False
                result.error_type = result.error_type or type(exc).__name__
                result.error_message = (result.error_message or "") + f"; driver cleanup: {exc}"
        try:
            await monitor.cleanup()
        except Exception as exc:
            result.success = False
            result.error_type = result.error_type or type(exc).__name__
            result.error_message = (result.error_message or "") + f"; process cleanup: {exc}"
        await monitor.stop()
        result.total_time_s = time.perf_counter() - started
        result.peak_memory_bytes = monitor.peak_memory_bytes
        result.cpu_time_s = monitor.cpu_time_s
        report = validate(extraction, scenario)
        result.extracted_record_count = len(extraction.records)
        result.duplicate_record_count = report.duplicate_record_count
        result.missing_required_fields = report.missing_required_fields
        result.validation_errors = report.errors
        result.success = result.success and report.valid
        result.settings["completion_evidence"] = extraction.evidence
        result.settings["expected_record_count"] = extraction.expected_count
        path = root / "extractions" / engine.value / scenario.value / f"{run_number}.json"
        try:
            write_extraction(path, extraction.records)
            result.extraction_path = str(path)
        except Exception as exc:
            result.success = False
            result.error_type = result.error_type or type(exc).__name__
            result.error_message = (result.error_message or "") + f"; extraction write: {exc}"
        append_result(root / "runs.jsonl", result)
    if cancelled:
        raise cancelled
    return result


def schedule(engines: list[Engine], scenarios: list[Scenario], runs: int, seed: int):
    rng = random.Random(seed)
    for warmup, round_number in [(True, 0), *[(False, n) for n in range(1, runs + 1)]]:
        for scenario in scenarios:
            order = list(engines)
            rng.shuffle(order)
            for engine in order:
                yield engine, scenario, warmup, round_number


async def benchmark(
    engines: list[Engine],
    scenarios: list[Scenario],
    runs: int,
    root: Path,
    settings: Settings,
    on_result: Callable[[RunResult], None] | None = None,
) -> list[RunResult]:
    policy = SitePolicy(settings.delay_s)
    preflight_error = None
    # Shared, untimed policy fetch; unavailable policy fails closed for all attempts.
    try:
        async with async_playwright() as playwright:
            request = await playwright.request.new_context()
            try:
                await policy.load(request)
            finally:
                await request.dispose()
    except Exception as exc:
        preflight_error = exc
    session_id = uuid4().hex
    first = next_run_number(root)
    results = []
    for engine, scenario, warmup, round_number in schedule(engines, scenarios, runs, settings.seed):
        result = await run_one(
            engine,
            scenario,
            first + round_number,
            warmup,
            root,
            session_id,
            settings,
            policy,
            preflight_error,
        )
        results.append(result)
        if on_result:
            on_result(result)
    return results
