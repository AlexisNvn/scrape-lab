import json

import pytest
from pydantic import ValidationError

from scrapeprint.models import Engine, RunResult, Scenario
from scrapeprint.storage import append_result, next_run_number, read_results, write_extraction
from scrapeprint.summary import percentile95, summarize


def result(**changes):
    return RunResult(
        session_id="test",
        engine=Engine.chromium,
        scenario=Scenario.products,
        run_number=1,
        **changes,
    )


def test_result_json_round_trip():
    original = result(error_type="TimeoutError", error_message="Unicode: café\nnext line")
    assert RunResult.model_validate_json(original.model_dump_json()) == original
    assert original.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    "field",
    ["startup_time_s", "total_time_s", "peak_memory_bytes", "cpu_time_s", "extracted_record_count"],
)
def test_negative_measurements_rejected(field):
    with pytest.raises(ValidationError):
        result(**{field: -1})


def test_jsonl_append_is_immediately_readable(tmp_path):
    path = tmp_path / "results" / "runs.jsonl"
    first = result(error_message="line one\nline two")
    append_result(path, first)
    assert read_results(path) == [first]
    second = result(success=True, extracted_record_count=28)
    append_result(path, second)
    assert read_results(path) == [first, second]
    assert len(path.read_text().splitlines()) == 2


def test_malformed_jsonl_reports_line(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(result().model_dump_json() + "\n{bad\n")
    with pytest.raises(ValueError, match=r":2: invalid result"):
        read_results(path)


def test_extraction_never_overwrites_and_allocates_next_number(tmp_path):
    path = tmp_path / "extractions/chromium/products/7.json"
    write_extraction(path, [{"name": "café"}])
    with pytest.raises(FileExistsError):
        write_extraction(path, [])
    assert json.loads(path.read_text(encoding="utf-8")) == [{"name": "café"}]
    assert next_run_number(tmp_path) == 8


def test_summary_excludes_warmups_and_failed_latencies():
    rows = [
        result(success=True, total_time_s=n, peak_memory_bytes=2**20, extracted_record_count=28)
        for n in (2, 4, 6)
    ]
    rows += [
        result(success=False, total_time_s=0.01),
        result(success=True, warmup=True, total_time_s=100),
    ]
    assert "| chromium | products | 3/4 | 75.0% | 4.000 | 6.000 | 1.00 | 28 |" in summarize(rows)


def test_summary_all_failed_and_empty():
    assert "0/1 | 0.0% | — | — | — | —" in summarize([result()])
    assert "| chromium" not in summarize([])


def test_p95_nearest_rank():
    assert percentile95([2]) == 2
    assert percentile95(list(range(1, 101))) == 95
