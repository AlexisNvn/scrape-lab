from scrapeprint.policy import ORIGIN
from scrapeprint.scenarios.base import REVIEW_JS, ScenarioContext


async def scrape(ctx: ScenarioContext) -> None:
    def is_reviews(response):
        return response.url == ORIGIN + "/api/graphql" and response.request.method == "POST"

    async with ctx.page.expect_response(is_reviews) as pending:
        await ctx.goto(ORIGIN + "/reviews")
    response = await pending.value
    expected = 0
    cursors = set()
    items = ctx.page.locator("#latest-reviews .review")
    for _ in range(ctx.max_steps):
        ctx.require(response.status == 200, f"Review API returned HTTP {response.status}")
        payload = await response.json()
        ctx.require(not payload.get("errors"), f"GraphQL errors: {payload.get('errors')}")
        data = payload["data"]["reviews"]
        edges = data["edges"]
        expected += len(edges)
        await ctx.page.wait_for_function(
            "n => document.querySelectorAll('#latest-reviews .review').length >= n && "
            "document.querySelector('#page-spinner')?.classList.contains('d-none')",
            arg=expected,
        )
        ctx.extraction.records = await items.evaluate_all(REVIEW_JS)
        # Compare each rendered page with the application's actual response, including metadata.
        rendered = ctx.extraction.records[-len(edges) :] if edges else []
        source = [
            {
                "kind": "review",
                "id": e["node"]["rid"],
                "text": e["node"]["text"],
                "date": e["node"]["date"],
                "rating": e["node"]["rating"],
            }
            for e in edges
        ]
        ctx.require(rendered == source, "Rendered reviews do not match the application's response")
        info = data["pageInfo"]
        ctx.require(type(info["hasNextPage"]) is bool, "Missing GraphQL completion signal")
        if not info["hasNextPage"]:
            ctx.extraction.expected_count = expected
            ctx.extraction.complete = True
            ctx.extraction.evidence = {"hasNextPage": False, "pages": len(cursors) + 1}
            return
        cursor = info["endCursor"]
        ctx.require(bool(edges) and cursor not in cursors, "Review cursor did not advance")
        cursors.add(cursor)
        async with ctx.page.expect_response(is_reviews) as pending:
            await ctx.page.locator("#page-load-more").click()
        response = await pending.value
    ctx.require(False, "Review pagination safety limit reached")
