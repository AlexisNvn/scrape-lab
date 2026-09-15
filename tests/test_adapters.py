import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import psutil
import pytest

from scrapeprint.adapters.chromium import ChromiumAdapter
from scrapeprint.adapters.obscura import ObscuraAdapter, ObscuraNotInstalledError, available_port


async def test_chromium_closes_browser_after_scenario_error():
    playwright = MagicMock()
    browser = AsyncMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    adapter = ChromiumAdapter()
    with pytest.raises(RuntimeError, match="extraction broke"):
        async with adapter.session(playwright, 1000):
            raise RuntimeError("extraction broke")
    browser.close.assert_awaited_once()


async def test_missing_obscura_has_installation_instructions(monkeypatch):
    monkeypatch.setattr("scrapeprint.adapters.obscura.shutil.which", lambda _: None)
    adapter = ObscuraAdapter()
    with pytest.raises(ObscuraNotInstalledError, match="Install an official release"):
        async with adapter.session(MagicMock(), 1000):
            pytest.fail("Missing engine must not yield")
    assert adapter.process is None


async def test_obscura_terminates_real_process_even_if_browser_close_raises():
    adapter = ObscuraAdapter()
    adapter.process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)"
    )
    process = adapter.process
    adapter.browser = AsyncMock()
    adapter.browser.close.side_effect = RuntimeError("CDP disconnected")
    with pytest.raises(RuntimeError, match="CDP disconnected"):
        await adapter.close()
    assert process.returncode is not None
    assert not psutil.pid_exists(process.pid)
    assert adapter.process is None


async def test_obscura_failed_cdp_start_cleans_subprocess(monkeypatch):
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)"
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("scrapeprint.adapters.obscura.find_obscura", lambda: "obscura")
    monkeypatch.setattr("scrapeprint.adapters.obscura.asyncio.create_subprocess_exec", spawn)
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    monkeypatch.setattr(
        "scrapeprint.adapters.obscura.asyncio.open_connection",
        AsyncMock(return_value=(None, writer)),
    )
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("CDP unsupported"))
    adapter = ObscuraAdapter()
    with pytest.raises(RuntimeError, match="CDP unsupported"):
        async with adapter.session(playwright, 1000):
            pass
    assert process.returncode is not None
    assert spawn.call_args.args[1] == "serve"
    endpoint = playwright.chromium.connect_over_cdp.call_args.args[0]
    assert endpoint.startswith("ws://127.0.0.1:")


def test_available_port_is_ephemeral():
    assert 1024 <= available_port() <= 65535
