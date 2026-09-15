import time
from dataclasses import dataclass, field

from playwright.async_api import Page

from scrapeprint.models import Extraction
from scrapeprint.policy import SitePolicy


class ExtractionError(RuntimeError):
    pass


@dataclass
class ScenarioContext:
    page: Page
    policy: SitePolicy
    extraction: Extraction = field(default_factory=Extraction)
    navigation_time_s: float = 0
    max_steps: int = 100

    async def goto(self, url: str) -> None:
        self.policy.check(url)
        start = time.perf_counter()
        try:
            response = await self.page.goto(url, wait_until="load")
            if response is None or response.status != 200:
                raise ExtractionError(
                    f"Navigation failed: {url}, HTTP "
                    f"{response.status if response else 'no response'}"
                )
            if self.policy.failures:
                raise ExtractionError("; ".join(self.policy.failures))
        finally:
            self.navigation_time_s += time.perf_counter() - start

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ExtractionError(message)


REVIEW_JS = """els => els.map(el => ({
    kind: 'review',
    id: el.getAttribute('data-review-id') ||
        [...el.classList].find(c => c.startsWith('review-'))?.slice(7) || '',
    text: el.querySelector('p')?.textContent.trim() || '',
    date: el.querySelector('span')?.textContent.trim() || '',
    rating: el.querySelectorAll('svg').length
}))"""
