# Verification — 2026-09-15

The repository is implemented, but the acceptance criterion requiring a green
Chromium products smoke test is **blocked by inconsistent live target data**.
Validation has not been relaxed to make incomplete extractions pass.

| Check | Outcome |
| --- | --- |
| Ruff lint (`ruff check .`) | Passed |
| Ruff formatting (`ruff format --check .`) | Passed, 27 Python files |
| pytest (`python -m pytest -q -p no:cacheprovider`) | Passed, 40 tests |
| Chromium products, warmup + measured run | Failed: 25 records; site advertises 28 across six pages, but page 6 is empty |
| Chromium testimonials, warmup + measured run | Passed: 60 records each |
| Chromium reviews, warmup + measured run | Passed: 96 records each |
| Chromium product_detail, warmup + measured run | Failed: the site's dynamically loaded review endpoint returned HTTP 500; one product and five initial reviews preserved |
| Chromium js_links, warmup + measured run | Passed: 1 record each |
| Obscura live smoke | Skipped: `obscura` is not installed/on PATH |
| Missing Obscura handling and process cleanup | Passed in pytest, including actual subprocess termination after a simulated CDP failure |

The live command was:

```powershell
$env:NODE_USE_SYSTEM_CA='1'
.\.tools\uv.exe run --offline scrapeprint run --engines chromium --scenarios all --runs 1
```

It used Python 3.12.14, Playwright 1.62.0, Chromium 151.0.7922.34, and order seed
369896550. Its warmup and measured artifact numbers are 5 and 6. Attempts 1–2
were interrupted by a prolonged environment interruption; attempts 3–4 exposed
the missing final pagination link. All history remains in `results/runs.jsonl`.

After the final live run exposed an empty page 6, the products scenario was
changed to inspect the server-rendered container without waiting for a nonexistent
product row. The subsequent unit checks passed, including a regression proving
that an empty final page still fails the advertised record-count check. That
small fail-fast change was not followed by another redundant live run. The live
products attempts therefore record the earlier selector timeout; the final code
reports the count mismatch directly.

The summary command was also exercised against the saved JSONL. Success-rate
denominators include the retained failed measured runs; successful-only latency
statistics do not include their timeouts. No benchmark headless Chromium process
remained after the live command finished.
