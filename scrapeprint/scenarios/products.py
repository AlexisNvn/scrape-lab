import re
from urllib.parse import parse_qs, urlsplit

from scrapeprint.policy import ORIGIN, target_url
from scrapeprint.scenarios.base import ScenarioContext

PRODUCT_JS = """els => els.map(el => ({
    kind: 'product',
    name: el.querySelector('h3 a')?.textContent.trim() || '',
    url: el.querySelector('h3 a')?.href || '',
    price: el.querySelector('.price')?.textContent.trim() || '',
    description: el.querySelector('.short-description')?.textContent.trim() || ''
}))"""


def canonical_page(url: str) -> str:
    parsed = urlsplit(url)
    if not target_url(url) or parsed.path != "/products":
        raise ValueError(f"Unexpected pagination URL: {url}")
    query = parse_qs(parsed.query)
    if set(query) - {"page"}:
        raise ValueError(f"Unexpected pagination filter: {url}")
    number = int(query.get("page", ["1"])[0])
    if number < 1:
        raise ValueError("Invalid page number")
    return ORIGIN + "/products" + (f"?page={number}" if number != 1 else "")


async def scrape(ctx: ScenarioContext) -> None:
    pending = [ORIGIN + "/products"]
    visited = set()
    advertised_pages = None
    while pending:
        url = pending.pop(0)
        if url in visited:
            continue
        ctx.require(len(visited) < ctx.max_steps, "Product pagination safety limit reached")
        await ctx.goto(url)
        # Products are server rendered: an empty loaded container is data.
        await ctx.page.locator(".products").wait_for(state="attached")
        ctx.extraction.records.extend(
            await ctx.page.locator(".products .product").evaluate_all(PRODUCT_JS)
        )
        meta = await ctx.page.locator(".paging-meta").inner_text()
        match = re.search(r"page (\d+) of total (\d+) results in (\d+) pages", meta)
        ctx.require(match is not None, f"Unrecognized pagination totals: {meta}")
        current, total, pages = map(int, match.groups())
        requested = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
        ctx.require(current == requested, "Server returned the wrong product page")
        ctx.require(ctx.extraction.expected_count in (None, total), "Product total changed mid-run")
        ctx.require(advertised_pages in (None, pages), "Product page count changed mid-run")
        ctx.extraction.expected_count = total
        advertised_pages = pages
        visited.add(url)
        links = await ctx.page.locator(".paging a[href]").evaluate_all(
            "els => els.map(e => e.href)"
        )
        pending.extend(
            canonical_page(link)
            for link in links
            if canonical_page(link) not in visited and canonical_page(link) not in pending
        )
        # The live site's pager can omit an advertised page. Its explicit page
        # total and observed ?page=N contract still identify that page reliably.
        ctx.require(1 <= pages <= ctx.max_steps, "Invalid advertised product page count")
        for number in range(1, pages + 1):
            advertised_url = canonical_page(f"{ORIGIN}/products?page={number}")
            if advertised_url not in visited and advertised_url not in pending:
                pending.append(advertised_url)
    ctx.require(len(visited) == advertised_pages, "Did not visit every advertised product page")
    ctx.extraction.evidence = {
        "visited_pages": sorted(visited),
        "advertised_pages": advertised_pages,
    }
    ctx.extraction.complete = True
