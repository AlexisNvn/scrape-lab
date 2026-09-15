import asyncio
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from playwright.async_api import APIRequestContext, Route

ORIGIN = "https://web-scraping.dev"
USER_AGENT = "Scrapeprint/0.1 (+https://web-scraping.dev; browser benchmark)"


class PolicyError(RuntimeError):
    pass


def target_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.netloc == "web-scraping.dev"


class SitePolicy:
    def __init__(self, delay: float = 2.0):
        self.delay = max(2.0, delay)
        self.robots: RobotFileParser | None = None
        self.last_request = 0.0
        self.lock = asyncio.Lock()
        self.failures: list[str] = []

    async def load(self, request: APIRequestContext) -> None:
        response = await request.get(
            ORIGIN + "/robots.txt",
            timeout=120_000,
            max_redirects=0,
            headers={"User-Agent": USER_AGENT},
        )
        self.last_request = time.monotonic()
        if response.status != 200:
            raise PolicyError(f"Cannot verify robots.txt: HTTP {response.status}")
        body = await response.text()
        if "<html" in body.lower() or "user-agent:" not in body.lower():
            raise PolicyError("robots.txt is not a valid robots policy")
        self.robots = RobotFileParser()
        self.robots.parse(body.splitlines())
        self.delay = max(self.delay, self.robots.crawl_delay(USER_AGENT) or 0)
        rate = self.robots.request_rate(USER_AGENT)
        if rate:
            self.delay = max(self.delay, rate.seconds / rate.requests)

    def check(self, url: str) -> None:
        if not target_url(url):
            raise PolicyError(f"URL outside the only allowed target: {url}")
        if not self.robots or not self.robots.can_fetch(USER_AGENT, url):
            raise PolicyError(f"robots.txt does not permit {url}")

    async def pace(self) -> None:
        async with self.lock:
            remaining = self.delay - (time.monotonic() - self.last_request)
            if remaining > 0:
                # Deliberate politeness delay, never an extraction readiness heuristic.
                await asyncio.sleep(remaining)
            self.last_request = time.monotonic()

    async def route(self, route: Route) -> None:
        request = route.request
        if self.failures:
            await route.abort()
            return
        # No external subresources and no image/media/font downloads in either engine.
        if not target_url(request.url) or request.resource_type in {"image", "media", "font"}:
            await route.abort()
            if request.is_navigation_request():
                self.failures.append(f"Blocked off-target navigation: {request.url}")
            return
        try:
            self.check(request.url)
        except PolicyError as exc:
            self.failures.append(str(exc))
            await route.abort()
            return
        await self.pace()
        if self.failures:
            await route.abort()
            return
        # fetch with redirects disabled prevents a redirected request escaping the allowlist.
        try:
            response = await route.fetch(max_redirects=0, timeout=120_000)
        except Exception as exc:
            self.failures.append(f"Request failed: {request.url}: {exc}")
            await route.abort()
            return
        if 300 <= response.status < 400 and response.status != 304:
            self.failures.append(f"Redirect refused: {request.url} (HTTP {response.status})")
            await route.abort()
            return
        if response.status in {401, 403, 429} or response.status >= 500:
            self.failures.append(f"HTTP {response.status}: {request.url}; no bypass or retry")
        await route.fulfill(response=response)
