"""Phase 0 step 4: check ad fixtures (quote-back, simple parse check, sanity) and compute the
status each ad would get under docs/architecture.md §5a (private crackit-app repo).

TEST SCRIPT, NOT the production verifier. See spikes/README.md.

Reads tests/fixtures/ads/*.json. Each fixture lists the raw files it was extracted from; those
raw copies live in spikes/data/step4/ (gitignored, never committed). The script:
  1. Quote-back: every filled field's quote (or every fragment, if a list) must appear in the
     raw text (whitespace/quote-mark normalised, case-insensitive). Fails loudly if not.
  2. Parse check ("double extraction" stand-in): a regex parser reads last_date / BPS / age
     from the quote and must agree with the extracted value.
  3. Sanity: closing date not before fetch date; BPS 1-22 or a known scale; min age < max age
     within 15-70; vacancies a positive integer.
  4. Writes completeness + status back into each fixture.

Usage:  .venv/bin/python step4_check_fixtures.py            # check + update fixtures
        .venv/bin/python step4_check_fixtures.py --dry-run  # check only
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures/ads"
DATA = ROOT / "spikes/data/step4"

FIELDS = ["org", "post_title", "bps", "vacancies", "age_limit", "qualification", "domicile_quota",
          "gender", "experience", "test_service", "last_date", "ad_no"]
KEY_FIELDS = ["post_title", "last_date", "bps", "age_limit", "qualification"]
NEEDS_UPLOAD_SOURCES = {"PPSC"}
NO_BPS_SOURCES = {"Join Pak Army", "Join PAF"}  # military ranks, BPS not applicable
SCALE = re.compile(r"\b(?:BPS|BS|PPS|SPPS|MP|SPS|EG|OG)\s*-?\s*(?:\d{1,2}|[IVX]+)\b|\bN/?A\b|Not Applicable|Lump ?sum", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def norm(s: str) -> str:
    s = (s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-"))
    return re.sub(r"\s+", " ", s).strip().lower()


def text_of(path: Path) -> str:
    if path.suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return norm("\n".join(p.extract_text() or "" for p in pdf.pages))
    raw = path.read_text(errors="ignore")
    if path.suffix in (".html", ".htm"):
        raw = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", raw, flags=re.S | re.I)
        raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return norm(raw)


def parse_dates(s: str) -> list[date]:
    out = []
    for d, m, y in re.findall(r"\b(\d{1,2})[-./](\d{1,2})[-./](\d{4})\b", s):
        out.append(date(int(y), int(m), int(d)))
    for y, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", s):
        out.append(date(int(y), int(m), int(d)))
    for d, mon, y in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(\d{4})\b", s):
        if mon[:3].lower() in MONTHS:
            out.append(date(int(y), MONTHS[mon[:3].lower()], int(d)))
    for mon, d, y in re.findall(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s+(\d{4})\b", s):
        if mon[:3].lower() in MONTHS:
            out.append(date(int(y), MONTHS[mon[:3].lower()], int(d)))
    return out


def fragments(quote) -> list[str]:
    return [quote] if isinstance(quote, str) else list(quote or [])


def check_fixture(fx: dict, texts: dict[str, str]) -> dict:
    fetched = date.fromisoformat(fx["fetched_at"][:10])
    res: dict = {"quote_back": {}, "parse_check": {}, "sanity": {}, "ocr_only_fields": [], "conflicts": []}
    filled, missing = [], []
    for name in FIELDS:
        f = fx["fields"].get(name) or {}
        if f.get("conflict"):
            res["conflicts"].append(name)
            found = all(norm(frag) in texts.get(c["from"], "") for c in f["conflict"] for frag in fragments(c["quote"]))
            res["quote_back"][f"{name} (conflicting values)"] = found
            if not found:
                print(f"  CONFLICT QUOTE NOT FOUND [{fx['fixture_id']}.{name}]", file=sys.stderr)
        if f.get("value") in (None, "", []):
            missing.append(name)
            continue
        filled.append(name)
        ok = True
        for src in [f] + f.get("also_from", []):
            body = texts.get(src.get("from", ""), "")
            for frag in fragments(src.get("quote")):
                if norm(frag) not in body:
                    ok = False
                    print(f"  QUOTE NOT FOUND [{fx['fixture_id']}.{name}] in {src.get('from')}: {frag!r}", file=sys.stderr)
        if not fragments(f.get("quote")):
            ok = False
        res["quote_back"][name] = ok
        corroborated = any(not s.get("from", "").endswith(".ocr.txt") for s in f.get("also_from", []))
        if f.get("from", "").endswith(".ocr.txt") and not corroborated:
            res["ocr_only_fields"].append(name)

    # parse check: regex reading of the quote must agree with the extracted value
    q = lambda n: " ".join(fragments((fx["fields"].get(n) or {}).get("quote")))  # noqa: E731
    v = lambda n: (fx["fields"].get(n) or {}).get("value")  # noqa: E731
    if v("last_date"):
        res["parse_check"]["last_date"] = date.fromisoformat(v("last_date")) in parse_dates(q("last_date"))
    if v("bps"):
        res["parse_check"]["bps"] = bool(SCALE.search(q("bps")))
    if isinstance(v("age_limit"), dict):
        nums = [int(n) for n in re.findall(r"\b(\d{2})(?:\.\d)?\b", q("age_limit"))]
        want = [x for x in (v("age_limit").get("min"), v("age_limit").get("max")) if x is not None]
        res["parse_check"]["age_limit"] = all(int(w) in nums for w in want)

    # sanity rules
    if v("last_date"):
        res["sanity"]["last_date_not_past"] = date.fromisoformat(v("last_date")) >= fetched
    if v("bps"):
        res["sanity"]["bps_known_scale"] = bool(SCALE.search(str(v("bps"))))
    if isinstance(v("age_limit"), dict):
        lo, hi = v("age_limit").get("min"), v("age_limit").get("max")
        res["sanity"]["age_range_ok"] = (hi is None or 15 <= hi <= 70) and (lo is None or 15 <= lo <= 70) and (lo is None or hi is None or lo < hi)
    if v("vacancies") is not None:
        res["sanity"]["vacancies_positive_int"] = isinstance(v("vacancies"), int) and v("vacancies") > 0

    key = [k for k in KEY_FIELDS if not (k == "bps" and fx["source_name"] in NO_BPS_SOURCES)]
    key_missing = [k for k in key if k in missing]
    reasons = []
    if fx["source_name"] in NEEDS_UPLOAD_SOURCES and key_missing:
        status = "needs_upload"
        reasons.append(f"details only in bot-blocked docs; missing {', '.join(key_missing)}")
    elif res["sanity"].get("last_date_not_past") is False or not fx.get("currently_open_at_fetch", True):
        status = "closed"
        reasons.append("closing date before fetch date (listing still shows it)")
    else:
        if key_missing:
            reasons.append(f"key fields missing: {', '.join(key_missing)}")
        if not all(res["quote_back"].values()):
            reasons.append("quote-back failed")
        if not all(res["parse_check"].values()):
            reasons.append("parse check disagrees")
        if not all(res["sanity"].values()):
            reasons.append("sanity rule failed")
        if res["conflicts"]:
            reasons.append(f"sources disagree on: {', '.join(res['conflicts'])}")
        ocr_keys = [k for k in res["ocr_only_fields"] if k in key]
        if ocr_keys:
            reasons.append(f"OCR-only key fields without a second source: {', '.join(ocr_keys)}")
        status = "needs_confirmation" if reasons else "auto_verified"
        if not reasons:
            reasons.append("all key fields quoted, parse + sanity checks pass")
    return {
        "checks": res,
        "completeness": {"filled": filled, "missing": missing, "key_missing": key_missing,
                         "filled_count": len(filled), "of": len(FIELDS)},
        "status_under_5a": status,
        "status_reason": "; ".join(reasons),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not DATA.exists():
        print(f"Raw copies not found in {DATA}. They're gitignored; re-fetch them to re-run quote-back.", file=sys.stderr)
        return 1
    bad = 0
    for path in sorted(FIXTURES.glob("*.json")):
        fx = json.loads(path.read_text())
        texts = {f: text_of(DATA / f) for f in fx["raw_files"]}
        out = check_fixture(fx, texts)
        if not all(out["checks"]["quote_back"].values()):
            bad += 1
        print(f"{fx['fixture_id']:16} {out['status_under_5a']:19} filled {out['completeness']['filled_count']:2}/{len(FIELDS)}  {out['status_reason']}")
        if not args.dry_run:
            fx.update(out)
            path.write_text(json.dumps(fx, ensure_ascii=False, indent=2) + "\n")
    print(f"\n{bad} fixture(s) with quote-back failures")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
