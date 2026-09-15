from unittest.mock import AsyncMock, MagicMock
from urllib.robotparser import RobotFileParser

import pytest

from scrapeprint.policy import ORIGIN, PolicyError, SitePolicy, target_url
from scrapeprint.scenarios.products import canonical_page


def test_url_allowlist_and_pagination_canonicalization():
    assert target_url(ORIGIN + "/products")
    assert not target_url("https://web-scraping.dev.evil.test/products")
    assert not target_url("http://web-scraping.dev/products")
    assert canonical_page(ORIGIN + "/products?page=1") == ORIGIN + "/products"
    with pytest.raises(ValueError):
        canonical_page(ORIGIN + "/products?category=apparel")


def test_robots_fail_closed_and_disallow():
    policy = SitePolicy()
    with pytest.raises(PolicyError):
        policy.check(ORIGIN + "/products")
    policy.robots = RobotFileParser()
    policy.robots.parse(["User-agent: *", "Disallow: /private"])
    policy.check(ORIGIN + "/products")
    with pytest.raises(PolicyError):
        policy.check(ORIGIN + "/private")


async def test_robots_delay_cannot_be_lowered():
    policy = SitePolicy(delay=2)
    request = MagicMock()
    response = MagicMock(status=200)
    response.text = AsyncMock(return_value="User-agent: *\nDisallow: /private\nCrawl-delay: 5")
    request.get = AsyncMock(return_value=response)
    await policy.load(request)
    assert policy.delay == 5
    assert request.get.call_args.kwargs["max_redirects"] == 0


async def test_redirect_is_refused_without_following():
    policy = SitePolicy()
    policy.robots = RobotFileParser()
    policy.robots.parse(["User-agent: *", "Allow: /"])
    policy.pace = AsyncMock()
    route = MagicMock()
    route.request.url = ORIGIN + "/products"
    route.request.resource_type = "document"
    route.fetch = AsyncMock(return_value=MagicMock(status=302))
    route.abort = AsyncMock()
    await policy.route(route)
    assert policy.failures
    route.fetch.assert_awaited_once_with(max_redirects=0, timeout=120_000)
    route.abort.assert_awaited_once()
