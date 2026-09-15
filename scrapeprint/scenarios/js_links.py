from scrapeprint.policy import ORIGIN
from scrapeprint.scenarios.base import ScenarioContext


async def scrape(ctx: ScenarioContext) -> None:
    await ctx.goto(ORIGIN + "/js-links")
    await ctx.page.locator('#container a[href="/js-links-target"]').wait_for(state="attached")
    ctx.extraction.records = await ctx.page.locator("#container a[href]").evaluate_all(
        "els => els.map(el => ({kind: 'link', url: el.href, label: el.textContent.trim()}))"
    )
    # This tiny application appends exactly one link on DOMContentLoaded.
    ctx.extraction.expected_count = 1
    ctx.require(
        ctx.extraction.records
        == [{"kind": "link", "url": ORIGIN + "/js-links-target", "label": "js target"}],
        "JS link does not match the application's known link contract",
    )
    ctx.extraction.complete = True
    ctx.extraction.evidence = {"terminal": "DOMContentLoaded-generated link present"}
