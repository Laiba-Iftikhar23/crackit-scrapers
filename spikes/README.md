# Phase 0 spike scripts

> ⚠️ **These are TEST SCRIPTS, NOT the production scraper.** They were used once in Phase 0 (22 Oct 2026) to check sources by hand. They have no tests, no database writes, no scheduling and no retries. The real scraper is built in Phase 2 (in this repo, `crackit_scrapers/`; design in `docs/architecture.md` §5 of the private `crackit-app` repo).

Results from running them are recorded in the project docs (`docs/sources.md` in the private `crackit-app` repo).

## What each script does

| Script | Phase 0 step | What it checks |
|---|---|---|
| `step1_robots_fetch.py` | Step 1 | For each source URL: reads `robots.txt` (RFC 9309 rules, including `*` and `$` wildcards and any `Content-Signal:` lines), then does **one** plain GET if allowed. Reports status, final URL, size, title, job-word hits, PDF link count, `noai` / meta robots, whether it looks like a JS-only shell, and whether a bot challenge page came back. |
| `step2_headless_spike.py` | Step 2 | Opens each listing page in headless Chromium (Playwright), only if `robots.txt` allows. Reports whether it rendered, BPS / date patterns seen in the rendered text, JSON calls the page made, and job-related links. Can save rendered text + screenshots. |

| `step4_check_fixtures.py` | Step 4 | Re-checks `tests/fixtures/ads/*.json` against the raw copies in `spikes/data/step4/` (gitignored): quote-back for every filled field, a regex parse check, sanity rules. Then writes completeness + the §5a status into each fixture. Needs `pdfplumber`. |

Steps 1 and 2 print one JSON object per URL.

## Rules built into both scripts

- **Honest user agent:** `CrackitBot/1.0 (+contact: crackitapp.team@gmail.com)`
- **robots.txt checked before every request.** Disallowed → not fetched. robots.txt 4xx → no rules (RFC 9309; a 401/403 counts as 4xx here, which is an **[ASSUMPTION]**). 5xx or unreachable → treated as "disallow all".
- **Polite:** 3–5 s between requests to the same host (the `--delay` value is clamped to that range).
- **TLS verification always ON.** The scripts use the OS trust store when the `truststore` package is installed. On macOS/Windows that fills in missing intermediate certificates, which fpsc.gov.pk and joinpakarmy.gov.pk need. `--ca-bundle` lets you pass a PEM file with the correct intermediates instead (that's the plan for production on Linux). Verification is never switched off.
- **No bypassing:** no captcha solving, no stealth plugins, no UA spoofing, no IP rotation. A Cloudflare challenge page is reported, not worked around.
- **No logins, no form submits, no secrets or keys** in the code.

## Setup

Python 3.12+.

```bash
cd spikes
python3 -m venv .venv
.venv/bin/pip install httpx truststore playwright pdfplumber
.venv/bin/playwright install chromium
```

`truststore` is optional but recommended (see TLS above). `.venv/` is covered by the repo `.gitignore`.

## Run

Step 1, all sources (takes a few minutes because of the delays):

```bash
.venv/bin/python step1_robots_fetch.py --out step1_results.jsonl
```

Step 1, a few sources, plus one extra URL:

```bash
.venv/bin/python step1_robots_fetch.py PPSC SPSC --url https://ppsc.gop.pk/JobDescription.aspx
```

Step 2, all sources, saving rendered text + screenshots:

```bash
.venv/bin/python step2_headless_spike.py --save spike_out
```

Step 2, one source:

```bash
.venv/bin/python step2_headless_spike.py ARMY
```

Run them from inside `spikes/` (step 2 imports helpers from step 1). Output files (`*.jsonl`, `spike_out/`) are scratch; don't commit them.

## Known limits

- Run from a laptop, not from GitHub Actions. Government sites may block cloud IPs, so re-test from Actions in Phase 2.
- "BPS / dates seen" is a regex over the page text. It shows *whether* the data is on the page, not that it parses correctly.
- A source with no open ads (FPSC, UTS, PAF on 22 Oct) renders fine but proves nothing about extraction.
