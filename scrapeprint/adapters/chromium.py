from playwright.async_api import Browser, Playwright

from scrapeprint.adapters.base import BrowserAdapter


class ChromiumAdapter(BrowserAdapter):
    async def start(self, playwright: Playwright, timeout_ms: int) -> Browser:
        self.browser = await playwright.chromium.launch(headless=True, timeout=timeout_ms)
        return self.browser
