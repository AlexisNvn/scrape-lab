import pytest

from scrapeprint.models import Extraction, Scenario
from scrapeprint.validation import validate


def product(**changes):
    return {
        "kind": "product",
        "name": "Chocolate",
        "price": "9.99",
        "url": "https://web-scraping.dev/product/1",
        "description": "Candy",
        **changes,
    }


def test_complete_valid_extraction():
    assert validate(
        Extraction(records=[product()], expected_count=1, complete=True), Scenario.products
    ).valid


def test_duplicates_use_identity_even_if_other_fields_differ():
    data = Extraction(records=[product(), product(name="Different")], complete=True)
    report = validate(data, Scenario.products)
    assert report.duplicate_record_count == 1
    assert not report.valid


def test_missing_fields_counted_per_record():
    data = Extraction(records=[product(name=" ", price=None), product(name="")], complete=True)
    report = validate(data, Scenario.products)
    assert report.missing_required_fields == {"product.name": 2, "product.price": 1}


@pytest.mark.parametrize(
    "changes",
    [
        {"price": "NaN"},
        {"price": "free"},
        {"price": "-1"},
        {"url": "https://example.com/product/1"},
    ],
)
def test_incorrect_fields_fail(changes):
    assert not validate(
        Extraction(records=[product(**changes)], complete=True), Scenario.products
    ).valid


@pytest.mark.parametrize(
    "records,total,complete", [([], 0, True), ([product()], 28, True), ([product()], 1, False)]
)
def test_empty_partial_or_unverified_extractions_fail(records, total, complete):
    assert not validate(
        Extraction(records=records, expected_count=total, complete=complete), Scenario.products
    ).valid


def test_product_detail_requires_reviews():
    assert not validate(
        Extraction(records=[product()], complete=True), Scenario.product_detail
    ).valid


def test_invalid_review_metadata():
    record = {"kind": "review", "id": "r1", "text": "Good", "rating": 6, "date": "bad"}
    assert not validate(Extraction(records=[record], complete=True), Scenario.reviews).valid


def test_distinct_testimonial_ids_with_identical_text_are_not_duplicates():
    records = [{"kind": "testimonial", "id": str(n), "text": "Good", "rating": 5} for n in range(2)]
    assert validate(Extraction(records=records, complete=True), Scenario.testimonials).valid
