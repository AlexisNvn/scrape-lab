import asyncio
import shutil
import socket
import subprocess
import tempfile

import psutil
from playwright.async_api import Browser, Playwright

from scrapeprint.adapters.base import BrowserAdapter
from scrapeprint.metrics import terminate_processes


class ObscuraNotInstalledError(RuntimeError):
    pass


def find_obscura() -> str:
    binary = shutil.which("obscura")
    if not binary:
        raise ObscuraNotInstalledError(
            "Obscura binary not found on PATH. Install an official release from "
            "https://github.com/h4ckf0r0day/obscura/releases (or build from source), "
            "add its directory to PATH, and verify `obscura --version`. See README.md."
        )
    return binary


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class ObscuraAdapter(BrowserAdapter):
    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.log = None

    async def start(self, playwright: Playwright, timeout_ms: int) -> Browser:
        binary = find_obscura()
        port = available_port()
        self.log = tempfile.TemporaryFile()
        self.process = await asyncio.create_subprocess_exec(
            binary,
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        async with asyncio.timeout(timeout_ms / 1000):
            while True:
                if self.process.returncode is not None:
                    self.log.seek(0)
                    detail = self.log.read(8192).decode(errors="replace")
                    raise RuntimeError(
                        f"obscura serve exited ({self.process.returncode}): {detail}"
                    )
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    # Poll subprocess readiness, not website content.
                    await asyncio.sleep(0.05)
            self.browser = await playwright.chromium.connect_over_cdp(
                f"ws://127.0.0.1:{port}/devtools/browser", timeout=timeout_ms
            )
        return self.browser

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            try:
                if self.process:
                    if self.process.returncode is None:
                        try:
                            root = psutil.Process(self.process.pid)
                            family = [root, *root.children(recursive=True)]
                        except psutil.NoSuchProcess:
                            family = []
                        await asyncio.to_thread(terminate_processes, family)
                    async with asyncio.timeout(10):
                        await self.process.wait()
            finally:
                self.process = None
                if self.log:
                    self.log.close()
                    self.log = None
