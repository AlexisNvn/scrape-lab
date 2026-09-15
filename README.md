# scrapeprint

A correctness-first, sequential Python benchmark of Playwright Chromium and
Obscura. The only scraping target is **https://web-scraping.dev**. Both engines
call the same async scenario functions; adapters only manage browser lifecycles.
There are no local web servers, dashboards, Parquet files, or concurrency tests.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Install uv using your package manager or its official installer, then run from
this repository:

```sh
uv python install 3.12
uv sync --locked
uv run playwright install chromium
```

On Linux, use `uv run playwright install --with-deps chromium` if browser system
libraries are missing. `uv.lock` pins the Python dependencies and Playwright
version; the matching browser is downloaded by Playwright. The locally downloaded
Windows uv executable, if present, can be invoked as `.\.tools\uv.exe`.

On a Windows machine with a trusted corporate CA, the setup used here required
`$env:UV_SYSTEM_CERTS='true'` for uv and `$env:NODE_USE_SYSTEM_CA='1'` for
Playwright downloads and requests. Configure your organization's trusted CA;
certificate verification is never disabled by this repository.

## Obscura setup

Download a binary for your platform from the
[official Obscura releases](https://github.com/h4ckf0r0day/obscura/releases), or
follow the project's [source build instructions](https://github.com/h4ckf0r0day/obscura).
Put the extracted binary directory on PATH. Where a release includes a worker
binary, keep it beside `obscura`.

```sh
obscura --version
obscura serve --help
```

Do not start a server manually for this benchmark. Each attempt launches an async
subprocess using `obscura serve --host 127.0.0.1 --port <dynamic-port>` and connects
through `playwright.chromium.connect_over_cdp()` to the local browser WebSocket
endpoint. This loopback connection controls the engine; it is not a scraping target.
There is no fixed port 9222, stealth mode, proxy rotation, or challenge solving.
The binary must support the CDP methods used by Playwright, including fresh
contexts, routing, evaluation, and input. Unsupported methods are benchmark
failures, not silently replaced by Chromium or a different extractor.

A missing binary produces `ObscuraNotInstalledError` with installation instructions
in the CLI and JSONL. Chromium still runs when both engines are selected. Obscura
is not installed automatically, and its version is not pinned by `uv.lock`.

## CLI

```sh
uv run scrapeprint run --engines chromium,obscura --scenarios all --runs 5
uv run scrapeprint run --engines chromium --scenarios products,reviews --runs 3
uv run scrapeprint summarize results/runs.jsonl
```

Scenario names are `products`, `testimonials`, `reviews`, `product_detail`, and
`js_links`. Comma-separated selections accept whitespace but reject duplicates
and unknown values. Defaults are both engines, all scenarios, and five measured
runs per pair.

```sh
uv run scrapeprint run --engines chromium --scenarios products --runs 1
uv run scrapeprint run --engines obscura --scenarios products --runs 1
uv run scrapeprint run --scenarios js_links --runs 3 --seed 42 --results-dir results/trial
uv run scrapeprint run --help
```

`--timeout` is the per-action timeout in seconds (120 by default).
`--run-timeout` bounds a whole attempt (900 seconds). `--delay` can increase the
minimum request spacing above two seconds; it cannot lower the site's crawl
delay. A full run can take many minutes because permitted stylesheet, script,
document, and API requests are all paced. Run only one CLI process at a time.
Exit code 0 means every attempt passed, 1 means at least one warmup or measured
attempt failed, and 2 indicates invalid CLI input or an unreadable results file.

## Extraction and validation

| Scenario | Shared extraction | Completion/correctness checks |
| --- | --- | --- |
| `products` | `.products .product`; name, price, URL, description; traverse all `.paging a[href]` links and advertised pages | Match `.paging-meta` total and page count; verify returned page number; normalize page 1; reject duplicates and missing fields |
| `testimonials` | Scroll the final `.testimonial` into view so its HTMX `revealed` trigger loads the next batch; collect ID, text, rating | Await response and DOM growth; final record has no `hx-get`; match summary's advertised total |
| `reviews` | Click `#page-load-more`; collect review ID, text, date, star count | Observe the page's GraphQL responses, compare every rendered batch to its response, require advancing cursors and `hasNextPage=false` |
| `product_detail` | Product JSON-LD plus displayed price; embedded initial reviews and Load More review pages | Compare rendered reviews with embedded/API records; require terminal button removal and advertised review count; one product plus all reviews |
| `js_links` | Wait for `#container`'s generated anchor; collect absolute URL and label | Verify the application's single known `/js-links-target` link and `js target` label |

Records are JSON objects with a `kind` field (`product`, `testimonial`, `review`,
or `link`). Product detail is a flat list containing one product and its reviews;
its record count includes both. The product retains JSON-LD in `metadata`.
The application's normal JavaScript supplies its own CSRF/HTMX headers: the
benchmark does not manufacture tokens or call alternate extraction APIs.
Response observation validates browser-rendered data rather than replacing it.

The products pager currently omits page 6 despite advertising six pages. The
scraper follows every pagination link and fills that gap using the explicit
advertised page count and the observed `?page=N` URL convention. An empty final
page does not excuse a mismatch with the advertised record total.

Validation rejects empty datasets, missing required fields, duplicate identities,
invalid prices/ratings/dates/URLs, mismatched advertised totals, and unverified
completion. Duplicate counts count occurrences after the first identity, using
URL for products/links and ID for reviews/testimonials. Duplicate records are
preserved in output. Missing fields are counted by kind and field, such as
`{"product.name": 2}`. Safety limits (100 pagination/scroll steps) and timeouts
are failures, never evidence that extraction finished. Partial records collected
before an error are saved.

## Methodology

1. Fetch and parse [robots.txt](https://web-scraping.dev/robots.txt) before browser
   measurements. If the policy cannot be verified, attempts fail closed.
2. Perform one warmup for every engine/scenario pair before any measured round.
   Randomize engine order independently in every scenario/round, including
   warmups. Persist the random seed and session ID for reproducibility.
3. Launch a new browser/Obscura process and a fresh non-persistent context for
   every attempt. Clear cookies explicitly. Local/session storage, IndexedDB,
   caches, and service workers are not reused between runs.
4. Use identical viewport (1280x720), benchmark user agent, `en-US` locale,
   timeouts, network policy, and scenario code for both engines.
5. Sample resources, validate extraction, close the browser and driver, terminate
   remaining owned process descendants, then immediately write that attempt.
   Normal errors, launch failures, and async cancellation follow cleanup paths.

All allowed HTTP requests are spaced by at least the larger of two seconds,
`--delay`, and robots crawl-delay/request-rate. The limiter spans engines and
runs. The policy applies to every requested URL; third-party resources and
image/media/font downloads are blocked identically. Stylesheets and scripts are
retained for rendering and scrolling. Service workers are blocked. Redirects
are refused so no off-target redirect can escape the allowlist. HTTP
401/403/429/5xx causes failure without bypass or application retry.

Routing uses Playwright `route.fetch(max_redirects=0)` and `route.fulfill()` to
enforce the no-redirect policy. **This standardizes HTTP transport through the
Playwright driver instead of benchmarking each engine's native network stack.**
It also disables normal browser HTTP caching and adds common instrumentation
overhead. Interpret results as this controlled scraping workload, not raw engine
network or full-media page-load performance.

### Measurements

| JSONL field | Definition |
| --- | --- |
| `startup_time_s` | Playwright driver startup, engine launch/CDP connection, fresh context, policy registration, and new page |
| `navigation_time_s` | Sum of all scenario `goto(..., wait_until="load")` calls, including politeness waits and failed navigation time |
| `extraction_time_s` | Remaining scenario time: readiness waits, scrolling/clicks, API loading, DOM extraction, validation; excludes `goto` time |
| `total_time_s` | Wall time from attempt start through cleanup; excludes robots preflight and result file writes |
| `peak_memory_bytes` | Largest sampled sum of RSS for the Python harness and its newly created descendant processes, including browser and Playwright driver |
| `cpu_time_s` | Sum of user + system CPU deltas for the harness and CPU time of new descendants during the attempt |

Resources are sampled with psutil every 50 ms. CPU samples are retained for
processes that exit. Process identity checks guard against PID reuse; pre-existing
descendants are excluded. Metrics include the harness to make sampling symmetric
between a launched Chromium and an external Obscura process. The version is the
engine version reported by Playwright/CDP; it is `unknown` if startup fails before
that value is available. Inspect the Obscura binary version separately when a
CDP implementation reports a compatibility version.

## Results and summary

Each attempt, including warmups and failures, is appended and flushed/fsynced to
`results/runs.jsonl`. Records are written immediately to
`results/extractions/{engine}/{scenario}/{run}.json`, including an empty list when
startup fails. All required correctness, timing, resource, error, and version
fields appear in every result. `settings` also includes completion evidence and
expected counts.

Run numbers are artifact identifiers: a new output directory uses 1 for the
warmup and 2 onward for measured rounds. Subsequent invocations continue after
the largest existing number. Paired engines/scenarios use the same round number.
Existing extraction files are never overwritten. Do not concurrently write to
the same directory. `session_id` identifies each invocation; use separate output
directories when comparing distinct settings, hosts, or versions.

The Markdown summary excludes warmups. Success rate uses all measured attempts;
time, memory, and record medians use **successful runs only**, so an empty fast
failure cannot win. p95 uses nearest rank (`ceil(0.95 * n)`); with few runs it is
usually the maximum. A group with no successful runs shows dashes. Malformed
JSONL fails with a line number rather than silently dropping failures.

Illustrative output only (not measured performance):

```text
| Engine | Scenario | Successful runs | Success rate | Median total (s) | p95 total (s) | Median peak memory (MiB) | Median extracted records |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chromium | products | 5/5 | 100.0% | 105.000 | 110.000 | 180.00 | 28 |
| obscura | products | 0/5 | 0.0% | — | — | — | — |
```

## Checks

See [VERIFICATION.md](VERIFICATION.md) for the actual checks and live-site
blockers observed during implementation. The current target advertises more
products than it serves and returns HTTP 500 for additional product-detail
reviews; these scenarios correctly fail rather than reporting partial data as
successful.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run scrapeprint run --engines chromium --scenarios products --runs 1
# When Obscura is installed:
uv run scrapeprint run --engines obscura --scenarios products --runs 1
```

Unit tests use mocked browser/API objects and short-lived Python subprocesses
for cleanup verification. They never scrape another website or start a fixture
server. Live smoke tests are explicit CLI commands, not part of pytest.

## Limitations

- This public site can change between runs. Validation checks the application's
  advertised totals and response/DOM agreement; it cannot independently prove the
  server itself supplied truthful data. JS-links has a deliberately strict known
  contract that must be reviewed if the target changes.
- Politeness delays, public network latency, OS caches, and system load can
  dominate timing. Warmups warm the OS/driver environment, not a reused browser
  profile. Small sample sizes do not support broad performance claims.
- RSS can double-count shared pages across processes; short-lived processes and
  sub-50-ms memory/CPU peaks can be missed. psutil sampling is not kernel-level
  peak accounting. Compare on the same otherwise idle machine.
- CDP support in Obscura may be incomplete. This benchmark requires the same
  capabilities from both engines; incompatibilities remain visible failures.
  See [Playwright's CDP documentation](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp).
- Cleanup handles ordinary exceptions and cancellation, not power loss or an
  uncatchable OS kill. Ephemeral port allocation has a small bind/release race;
  a collision fails startup instead of selecting a fixed port or hiding retries.
- No parallel load tests, local fixtures, dashboard, Parquet, stealth/bypass,
  or automatic CAPTCHA solving are included in this MVP.
