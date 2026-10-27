"""Phase 0 step 1 spike: robots.txt check + one polite plain GET per URL.

TEST SCRIPT, NOT the production scraper. See spikes/README.md.

Rules it follows: honest UA, robots.txt checked before every fetch (RFC 9309 matching,
incl. `*` and `$`), 3-5 s between requests to the same host, TLS verification always on,
no captcha / bot-detection bypass, no logins, no secrets.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

UA = "CrackitBot/1.0 (+contact: crackitapp.team@gmail.com)"
UA_TOKEN = "crackitbot"
MIN_DELAY, MAX_DELAY = 3.0, 5.0

# Exact listing URLs checked on 22 Oct 2026 (see docs/sources.md in the private crackit-app repo).
DEFAULT_URLS = {
    "FPSC": "https://fpsc.gov.pk/Jobs",
    "NJP": "https://njp.gov.pk/jobs/live",
    "NTS": "https://nts.org.pk/new/projectsnew.php",
    "PTS": "https://pts.org.pk/Projects/",
    "OTS": "https://ots.org.pk/",
    "UTS": "https://uts.com.pk/jobs",
    "FGEI": "https://fgei.gov.pk/",
    "FIA": "https://fia.gov.pk/careers",
    "ASF": "https://joinasf.gov.pk/",
    "PID": "https://pid.gov.pk/advertisement",
    "APP": "https://www.app.com.pk/",
    "JANG": "https://jang.com.pk/jobs/latest",
    "ARMY": "https://joinpakarmy.gov.pk/",
    "PAF": "https://joinpaf.gov.pk/",
    "NAVY": "https://joinpaknavy.gov.pk/",
    "PPSC": "https://ppsc.gop.pk/Jobs.aspx",
    "PJOBS": "https://jobs.punjab.gov.pk/new_recruit/jobs",
    "SPSC": "https://spsc.gov.pk/advertisement.php",
    "IWORK": "https://iwork4sindh.com/public/employer/sjp",
    "SINDH": "https://sindh.gov.pk/jobs",
    "SJP_GOS": "https://sjp.gos.pk/",
    "STS": "https://sts.net.pk/",
}

JOB_WORDS = re.compile(r"\b(advertisement|vacanc\w*|recruit\w*|jobs?|posts?|BPS|closing date|last date|apply)\b", re.I)
CHALLENGE = re.compile(r"just a moment|cf-chl|challenge-platform|verify you are human|g-recaptcha|h-captcha", re.I)


def tls_context(ca_bundle: str | None) -> ssl.SSLContext | str | bool:
    """Verification is always on. Prefer the OS trust store (fills in missing intermediates
    on macOS/Windows); `--ca-bundle` adds pinned intermediates, as production will."""
    if ca_bundle:
        return ca_bundle
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True  # httpx default: certifi, verification on


# ---------- robots.txt (RFC 9309) ----------

@dataclass
class Robots:
    status: str
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, path pattern)
    allow_all: bool = False
    disallow_all: bool = False
    content_signals: list[str] = field(default_factory=list)

    def allows(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all or not self.rules:
            return True
        p = urlparse(url)
        path = (p.path or "/") + (f"?{p.query}" if p.query else "")
        best: tuple[int, bool] | None = None
        for allow, pattern in self.rules:
            if pattern and _matches(pattern, path):
                cand = (len(pattern), allow)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                    best = cand
        return True if best is None else best[1]


def _matches(pattern: str, path: str) -> bool:
    regex = "^" + re.escape(pattern).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def parse_robots(text: str) -> Robots:
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    signals: list[str] = []
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(val.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if key in ("allow", "disallow"):
            rules.append((key == "allow", val))
        elif key == "content-signal":
            signals.append(val)
    if agents or rules:
        groups.append((agents, rules))
    mine = [r for a, r in groups if any(UA_TOKEN in x for x in a)]
    star = [r for a, r in groups if "*" in a]
    chosen = mine or star
    merged = [rule for g in chosen for rule in g]
    return Robots(status="200", rules=merged, content_signals=signals)


class Polite:
    def __init__(self, delay: float) -> None:
        self.delay = min(max(delay, MIN_DELAY), MAX_DELAY)
        self.last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        gap = self.last.get(host, 0) + self.delay - time.time()
        if gap > 0:
            time.sleep(gap)
        self.last[host] = time.time()


class RobotsCache:
    def __init__(self, client: httpx.Client, polite: Polite) -> None:
        self.client, self.polite, self.cache = client, polite, {}

    def get(self, url: str) -> Robots:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base in self.cache:
            return self.cache[base]
        self.polite.wait(p.netloc)
        try:
            r = self.client.get(base + "/robots.txt")
            ctype = r.headers.get("content-type", "").lower()
            if r.status_code == 200 and "html" not in ctype:
                rb = parse_robots(r.text)
            elif r.status_code == 200:
                rb = Robots(status="200 (HTML page, treated as no rules)", allow_all=True)
            elif 400 <= r.status_code < 500:
                # RFC 9309 §2.3.1.3: 4xx = "unavailable" -> crawler may access everything. [ASSUMPTION for 401/403]
                rb = Robots(status=f"{r.status_code} (4xx = no rules per RFC 9309)", allow_all=True)
            else:
                # RFC 9309 §2.3.1.4: 5xx = "unreachable" -> assume complete disallow.
                rb = Robots(status=f"{r.status_code} (5xx = treat as disallow all)", disallow_all=True)
        except httpx.HTTPError as e:
            rb = Robots(status=f"error: {type(e).__name__}: {str(e)[:120]}", disallow_all=True)
        self.cache[base] = rb
        return rb


def check(client: httpx.Client, robots: RobotsCache, polite: Polite, name: str, url: str) -> dict:
    rb = robots.get(url)
    out: dict = {"name": name, "url": url, "robots": rb.status, "robots_allows": rb.allows(url)}
    if rb.content_signals:
        out["content_signals"] = rb.content_signals
    if not out["robots_allows"]:
        out["fetched"] = False
        return out
    polite.wait(urlparse(url).netloc)
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return out
    body = r.text
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S | re.I)
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    out.update(
        status=r.status_code,
        final_url=str(r.url),
        content_type=r.headers.get("content-type", "")[:40],
        bytes=len(r.content),
        title=title.group(1).strip()[:90] if title else "",
        job_word_hits=len(JOB_WORDS.findall(visible)),
        pdf_links=len(re.findall(r"href=[\"'][^\"']+\.pdf", body, re.I)),
        meta_robots=re.findall(r"<meta[^>]+name=[\"']robots[\"'][^>]*>", body, re.I)[:2],
        noai="noai" in body.lower(),
        js_shell=bool(re.search(r"id=[\"'](root|app|__next)[\"']|<app-root|ng-version|_next/static", body, re.I)),
        bot_challenge=bool(CHALLENGE.search(body)),
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help=f"source keys (default: all). Known: {', '.join(DEFAULT_URLS)}")
    ap.add_argument("--url", action="append", default=[], help="extra URL to check (repeatable)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests per host (clamped to 3-5)")
    ap.add_argument("--ca-bundle", help="PEM file incl. intermediates (verification stays on)")
    ap.add_argument("--out", help="write JSON lines here as well as stdout")
    args = ap.parse_args()

    targets = [(n, DEFAULT_URLS[n]) for n in (args.names or DEFAULT_URLS)] + [(u, u) for u in args.url]
    polite = Polite(args.delay)
    sink = open(args.out, "w") if args.out else None
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True,
                      verify=tls_context(args.ca_bundle)) as client:
        robots = RobotsCache(client, polite)
        for name, url in targets:
            line = json.dumps(check(client, robots, polite, name, url), ensure_ascii=False)
            print(line, flush=True)
            if sink:
                sink.write(line + "\n")
    if sink:
        sink.close()


if __name__ == "__main__":
    sys.exit(main())
