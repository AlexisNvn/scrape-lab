import json
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from scrapeprint.models import Extraction, Scenario, Validation

REQUIRED = {
    "product": ("name", "price", "url", "description"),
    "review": ("id", "text", "date", "rating"),
    "testimonial": ("id", "text", "rating"),
    "link": ("url", "label"),
}
KINDS = {
    Scenario.products: {"product"},
    Scenario.testimonials: {"testimonial"},
    Scenario.reviews: {"review"},
    Scenario.product_detail: {"product", "review"},
    Scenario.js_links: {"link"},
}


def validate(extraction: Extraction, scenario: Scenario) -> Validation:
    report = Validation()
    seen = set()
    if not extraction.complete:
        report.errors.append("No verified completion signal")
    if not extraction.records:
        report.errors.append("No records extracted")
    if (
        extraction.expected_count is not None
        and len(extraction.records) != extraction.expected_count
    ):
        report.errors.append(
            f"Expected {extraction.expected_count} records, got {len(extraction.records)}"
        )
    for index, record in enumerate(extraction.records):
        kind = record.get("kind")
        if kind not in KINDS[scenario]:
            report.errors.append(f"Record {index}: unexpected kind {kind!r}")
            continue
        for field in REQUIRED[kind]:
            value = record.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                key = f"{kind}.{field}"
                report.missing_required_fields[key] = report.missing_required_fields.get(key, 0) + 1
        identity = record.get("url") if kind in {"product", "link"} else record.get("id")
        key = (kind, str(identity) if identity else json.dumps(record, sort_keys=True))
        if key in seen:
            report.duplicate_record_count += 1
        seen.add(key)
        try:
            if kind in {"product", "link"}:
                url = urlsplit(str(record.get("url", "")))
                if url.scheme != "https" or url.netloc != "web-scraping.dev":
                    raise ValueError("URL outside target origin")
            if kind == "product":
                price = Decimal(str(record.get("price")))
                if not price.is_finite() or price <= 0:
                    raise ValueError("invalid price")
            if kind in {"review", "testimonial"}:
                rating = record.get("rating")
                if type(rating) is not int or not 1 <= rating <= 5:
                    raise ValueError("rating must be an integer from 1 to 5")
            if kind == "review":
                date.fromisoformat(str(record.get("date")))
        except (ValueError, InvalidOperation) as exc:
            report.errors.append(f"Record {index}: {exc}")
    if scenario == Scenario.product_detail:
        kinds = [r.get("kind") for r in extraction.records]
        if kinds.count("product") != 1 or not kinds.count("review"):
            report.errors.append("Expected one product and its reviews")
    return report
