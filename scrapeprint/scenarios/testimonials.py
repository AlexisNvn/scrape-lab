import re

from scrapeprint.policy import ORIGIN
from scrapeprint.scenarios.base import ScenarioContext

TESTIMONIAL_JS = """els => els.map(el => ({
    kind: 'testimonial',
    id: el.querySelector('identicon-svg')?.getAttribute('username') || '',
    text: el.querySelector('.text')?.textContent.trim() || '',
    rating: el.querySelectorAll('.rating svg').length
}))"""


async def scrape(ctx: ScenarioContext) -> None:
    await ctx.goto(ORIGIN + "/testimonials")
    summary = await ctx.page.locator(".testimonials-summary").inner_text()
    total = re.search(r"in\s+(\d+)\s+Reviews", summary)
    ctx.require(total is not None, "Missing advertised testimonial total")
    ctx.extraction.expected_count = int(total.group(1))
    items = ctx.page.locator(".testimonial")
    await items.first.wait_for()
    for _ in range(ctx.max_steps):
        ctx.extraction.records = await items.evaluate_all(TESTIMONIAL_JS)
        # Only the last record's HTMX revealed sentinel can request the next batch.
        last = items.last
        next_url = await last.get_attribute("hx-get")
        if not next_url:
            ctx.extraction.complete = True
            ctx.extraction.evidence = {"terminal": "last testimonial has no hx-get"}
            return
        ctx.policy.check(next_url)
        before = await items.count()
        async with ctx.page.expect_response(lambda r, url=next_url: r.url == url) as pending:
            await last.scroll_into_view_if_needed()
        response = await pending.value
        ctx.require(response.status == 200, f"Testimonials returned HTTP {response.status}")
        await ctx.page.wait_for_function(
            "n => document.querySelectorAll('.testimonial').length > n", arg=before
        )
    ctx.require(False, "Infinite-scroll safety limit reached without a terminal sentinel")
