# crackit-scrapers

Scrapers for **Crackit**, a free prep app for Pakistani government job tests. This repo collects **currently open government job ads from official sources only** (Federal, Punjab and Sindh) so the app can show them with a citation and check eligibility.

The app itself lives in a separate private repo.

## What's here

| Path | What it is |
|---|---|
| `spikes/` | Phase 0 **test scripts** (robots.txt + fetch check, headless spike, fixture checker). Not the production scraper. See `spikes/README.md`. |
| `tests/fixtures/ads/` | 22 real ads (Oct 2026) with every extracted field tied to an exact quote from the official source. Used to test parsers and the auto-verifier. |
| `crackit_scrapers/` | The production scraper (built in Phase 2). |

## How we scrape

- **Official sources only.** Every ad links back to the official page it came from. Aggregator sites are never a source.
- **robots.txt is respected** on every request (RFC 9309 rules, including wildcards). Disallowed means not fetched.
- **No bypassing**: no captcha solving, no bot-detection workarounds, no logins, no IP rotation, no user-agent spoofing.
- **Polite**: honest user agent `CrackitBot/1.0 (+contact: crackitapp.team@gmail.com)`, 3–5 s between requests to the same site, schedules every few hours.
- **TLS verification is always on.**
- **Official documents are never committed or re-hosted.** Raw downloads stay in gitignored folders (`spikes/data/`).

## Secrets

This repo is **public**. It contains **no keys, tokens or passwords**, and none may ever be committed. Credentials (database, AI API, error tracking) live only in **GitHub Secrets** and are read from environment variables at run time. Workflow logs are public too, so code never prints secrets or user data.

## Contact

If you run one of the sites we read and want us to stop or slow down, email **crackitapp.team@gmail.com** and we'll act on it.

## Licence

No licence is granted: **all rights reserved**. You may read the code here, but not copy, modify or redistribute it without permission.
