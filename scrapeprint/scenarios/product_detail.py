import json

from scrapeprint.policy import ORIGIN
from scrapeprint.scenarios.base import REVIEW_JS, ScenarioContext


async def scrape(ctx: ScenarioContext) -> None:
    await ctx.goto(ORIGIN + "/product/1")
    ld = json.loads(await ctx.page.locator('script[type="application/ld+json"]').inner_text())
    ctx.require(ld.get("@type") == "Product", "Missing Product structured data")
    product = {
        "kind": "product",
        "name": ld.get("name"),
        "description": ld.get("description"),
        "price": (await ctx.page.locator(".product-price").inner_text()).strip().lstrip("$"),
        "url": ORIGIN + "/product/1",
        "metadata": ld,
    }
    expected = int(ld["aggregateRating"]["reviewCount"])
    ctx.extraction.expected_count = 1 + expected
    ctx.extraction.records = [product]
    initial = json.loads(await ctx.page.locator("#reviews-data").inner_text())
    await ctx.page.wait_for_function(
        "n => document.querySelectorAll('#reviews .review').length >= n", arg=len(initial)
    )
    source = list(initial)
    items = ctx.page.locator("#reviews .review")
    for _ in range(ctx.max_steps):
        reviews = await items.evaluate_all(REVIEW_JS)
        ctx.extraction.records = [product, *reviews]
        expected_reviews = [
            {
                "kind": "review",
                "id": r["id"],
                "text": r["text"],
                "date": r["date"],
                "rating": r["rating"],
            }
            for r in source
        ]
        ctx.require(reviews == expected_reviews, "Product reviews differ from embedded/API data")
        button = ctx.page.locator("#load-more-reviews")
        if await button.count() == 0:
            ctx.extraction.complete = True
            ctx.extraction.evidence = {"review_count": expected, "terminal": "load-more removed"}
            return
        previous_page = await ctx.page.locator("#reviews").get_attribute("data-page")
        async with ctx.page.expect_response(
            lambda r: r.url.startswith(ORIGIN + "/api/reviews?")
        ) as pending:
            await button.click()
        response = await pending.value
        ctx.require(response.status == 200, f"Product reviews returned HTTP {response.status}")
        payload = await response.json()
        source.extend(payload["results"])
        await ctx.page.wait_for_function(
            "previous => document.querySelector('#reviews').dataset.page !== previous",
            arg=previous_page,
        )
    ctx.require(False, "Product review pagination safety limit reached")
