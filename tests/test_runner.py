import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scrapeprint.models import Engine, Scenario
from scrapeprint.policy import SitePolicy
from scrapeprint.runner import Settings, run_one, schedule
from scrapeprint.storage import read_results


def test_schedule_has_one_warmup_per_pair_and_reproducible_random_order():
    args = (list(Engine), list(Scenario), 3, 41)
    plan = list(schedule(*args))
    assert plan == list(schedule(*args))
    assert len(plan) == 40
    assert sum(w for _, _, w, _ in plan) == 10
    assert all(w for _, _, w, _ in plan[:10])
    orders = {tuple(row[0] for row in plan[i : i + 2]) for i in range(0, len(plan), 2)}
    assert len(orders) == 2


async def test_preflight_failure_is_persisted_without_launch(tmp_path):
    result = await run_one(
        Engine.chromium,
        Scenario.products,
        1,
        False,
        tmp_path,
        "test",
        Settings(),
        SitePolicy(),
        RuntimeError("robots unavailable"),
    )
    assert not result.success
    assert result.error_message == "robots unavailable"
    assert read_results(tmp_path / "runs.jsonl") == [result]
    assert (tmp_path / "extractions/chromium/products/1.json").read_text().strip() == "[]"


@pytest.mark.parametrize("cancel", [False, True])
async def test_runner_preserves_partial_records_and_cleans_after_error(
    tmp_path, monkeypatch, cancel
):
    browser = MagicMock(version="test-engine")
    context = MagicMock()
    context.clear_cookies = AsyncMock()
    context.route = AsyncMock()
    context.new_page = AsyncMock(return_value=MagicMock())
    browser.new_context = AsyncMock(return_value=context)
    adapter = MagicMock()
    adapter.start = AsyncMock(return_value=browser)
    adapter.close = AsyncMock()
    monkeypatch.setitem(
        __import__("scrapeprint.runner", fromlist=["ADAPTERS"]).ADAPTERS,
        Engine.chromium,
        lambda: adapter,
    )
    driver = MagicMock()
    driver.stop = AsyncMock()
    manager = MagicMock()
    manager.start = AsyncMock(return_value=driver)
    monkeypatch.setattr("scrapeprint.runner.async_playwright", lambda: manager)

    async def broken(ctx):
        ctx.extraction.records.append({"kind": "product", "name": "partial"})
        if cancel:
            raise asyncio.CancelledError()
        raise RuntimeError("extraction broke")

    monkeypatch.setitem(
        __import__("scrapeprint.runner", fromlist=["SCENARIOS"]).SCENARIOS,
        Scenario.products,
        broken,
    )
    attempt = run_one(
        Engine.chromium, Scenario.products, 1, False, tmp_path, "test", Settings(), SitePolicy()
    )
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await attempt
    else:
        await attempt
    adapter.close.assert_awaited_once()
    driver.stop.assert_awaited_once()
    [result] = read_results(tmp_path / "runs.jsonl")
    assert not result.success
    assert result.extracted_record_count == 1
    assert result.missing_required_fields["product.price"] == 1
