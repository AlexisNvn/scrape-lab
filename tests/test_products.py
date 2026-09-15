from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from scrapeprint.models import Scenario
from scrapeprint.policy import ORIGIN
from scrapeprint.scenarios.base import ScenarioContext
from scrapeprint.scenarios.products import scrape
from scrapeprint.validation import validate


@pytest.mark.parametrize("last_page_count", [3, 0])
async def test_products_visits_advertised_final_page_missing_from_pager(last_page_count):
    page = MagicMock()
    current = 1
    visited = []

    async def goto(url):
        nonlocal current
        current = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
        visited.append(current)

    async def records(_):
        count = 5 if current < 6 else last_page_count
        return [
            {
                "kind": "product",
                "name": f"Product {current}-{i}",
                "price": "9.99",
                "description": "Description",
                "url": f"{ORIGIN}/product/{(current - 1) * 5 + i + 1}",
            }
            for i in range(count)
        ]

    items = MagicMock()
    items.wait_for = AsyncMock()
    items.evaluate_all = records
    meta = MagicMock()

    async def text():
        return f"page {current} of total 28 results in 6 pages"

    meta.inner_text = text
    pager = MagicMock()
    pager.evaluate_all = AsyncMock(
        return_value=[f"{ORIGIN}/products?page={n}" for n in range(1, 6)]
    )
    page.locator.side_effect = lambda selector: {
        ".products": items,
        ".products .product": items,
        ".paging-meta": meta,
        ".paging a[href]": pager,
    }[selector]
    ctx = ScenarioContext(page, MagicMock())
    ctx.goto = goto
    await scrape(ctx)
    assert visited == [1, 2, 3, 4, 5, 6]
    assert validate(ctx.extraction, Scenario.products).valid == (last_page_count == 3)
    assert len(ctx.extraction.records) == 25 + last_page_count
