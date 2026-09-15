import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

from playwright.async_api import Browser, Playwright


class BrowserAdapter(ABC):
    browser: Browser | None = None

    @abstractmethod
    async def start(self, playwright: Playwright, timeout_ms: int) -> Browser:
        """Launch a fresh engine instance."""

    async def close(self) -> None:
        if self.browser:
            try:
                async with asyncio.timeout(10):
                    await self.browser.close()
            finally:
                self.browser = None

    @asynccontextmanager
    async def session(self, playwright: Playwright, timeout_ms: int):
        try:
            yield await self.start(playwright, timeout_ms)
        finally:
            await self.close()
