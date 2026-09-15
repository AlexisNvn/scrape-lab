from scrapeprint.models import Scenario
from scrapeprint.scenarios import js_links, product_detail, products, reviews, testimonials

SCENARIOS = {
    Scenario.products: products.scrape,
    Scenario.testimonials: testimonials.scrape,
    Scenario.reviews: reviews.scrape,
    Scenario.product_detail: product_detail.scrape,
    Scenario.js_links: js_links.scrape,
}
