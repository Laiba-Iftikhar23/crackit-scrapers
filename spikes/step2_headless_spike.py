"""Phase 0 step 2 spike: does the job listing render in a headless browser, and can
title / BPS / dates be seen in the rendered text?

TEST SCRIPT, NOT the production scraper. See spikes/README.md.

Rules it follows: honest UA, robots.txt checked for every URL (same RFC 9309 parser as
step 1), 3-5 s between page loads per host, TLS verification ON (Chromium's normal
certificate checks; `ignore_https_errors` is never set), no captcha / bot-detection
bypass, no logins, no form submits, no secrets.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import Page, sync_playwright

from step1_robots_fetch import UA, Polite, RobotsCache, tls_context

# Listing pages from the 22 Oct 2026 spike (see docs/sources.md in the private crackit-app repo).
DEFAULT_URLS = {
    "FPSC": ["https://fpsc.gov.pk/Jobs"],
    "NTS": ["https://nts.org.pk/new/projectsnew.php"],
    "PTS": ["https://pts.org.pk/Projects/"],
    "UTS": ["https://uts.com.pk/jobs"],
    "STS": ["https://sts.net.pk/", "https://apply.sts.net.pk/results"],
    "ARMY": ["https://joinpakarmy.gov.pk/"],
    "PAF": ["https://joinpaf.gov.pk/"],
}

JOB_LINK = re.compile(r"job|career|advert|vacanc|recruit|project|announce|opening|induct|course", re.I)
BPS = re.compile(r"\b(?:BPS|BS|PPS|SPS)\s*[-–]?\s*\d{1,2}\b", re.I)
DATE = re.compile(
    r"\b\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3,9})[-/.]\d{2,4}\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]{2,8},?\s+\d{4}\b"
    r"|\b[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4}\b"
)
CHALLENGE = re.compile(r"just a moment|verify you are human|captcha|access denied", re.I)
NOISE = re.compile(r"google|analytics|facebook|doubleclick|cdn-cgi|\.(png|jpe?g|svg|gif|woff2?|css)(\?|$)", re.I)


def visit(page: Page, url: str, robots: RobotsCache, polite: Polite, out_dir: Path | None, tag: str) -> dict:
    rb = robots.get(url)
    res: dict = {"url": url, "robots": rb.status, "robots_allows": rb.allows(url)}
    if not res["robots_allows"]:
        return res

    calls: list[str] = []
    page.on("response", lambda r: calls.append(f"{r.status} {r.request.method} {r.url}")
            if r.request.resource_type in ("xhr", "fetch") else None)
    polite.wait(urlparse(url).netloc)
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=45_000)
        res["status"] = resp.status if resp else None
    except Exception as e:  # slow sites may never go idle; still read what rendered
        res["goto_error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:140]}"
    page.wait_for_timeout(2500)

    text = page.inner_text("body") if page.query_selector("body") else ""
    host = urlparse(page.url).netloc.removeprefix("www.")
    links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText.trim().slice(0, 70), e.href])")
    res.update(
        final_url=page.url,
        title=page.title()[:80],
        text_chars=len(text),
        bps_seen=BPS.findall(text)[:6],
        dates_seen=DATE.findall(text)[:6],
        bot_challenge=bool(CHALLENGE.search(text)),
        json_calls=[c for c in calls if not NOISE.search(c)][:12],
        job_links=[[t, h] for t, h in links
                   if JOB_LINK.search(f"{t} {h}") and urlparse(h).netloc.removeprefix("www.").endswith(host.split(".", 1)[-1])][:15],
    )
    if out_dir:
        (out_dir / f"{tag}.txt").write_text(text)
        page.screenshot(path=str(out_dir / f"{tag}.png"))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help=f"source keys (default: all). Known: {', '.join(DEFAULT_URLS)}")
    ap.add_argument("--url", action="append", default=[], help="extra URL to render (repeatable)")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between loads per host (clamped to 3-5)")
    ap.add_argument("--ca-bundle", help="PEM file incl. intermediates, used for robots.txt requests")
    ap.add_argument("--save", help="folder for rendered text + screenshots (optional)")
    args = ap.parse_args()

    targets = [(n, u) for n in (args.names or DEFAULT_URLS) for u in DEFAULT_URLS[n]] + [(u, u) for u in args.url]
    out_dir = Path(args.save) if args.save else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    polite = Polite(args.delay)

    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True,
                      verify=tls_context(args.ca_bundle)) as client, sync_playwright() as pw:
        robots = RobotsCache(client, polite)
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        for i, (name, url) in enumerate(targets):
            page = ctx.new_page()
            res = visit(page, url, robots, polite, out_dir, f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', name)[:40]}")
            page.close()
            print(json.dumps({"name": name, **res}, ensure_ascii=False), flush=True)
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
