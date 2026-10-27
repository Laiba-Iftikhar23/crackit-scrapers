"""Schema checks for the ad fixtures in tests/fixtures/ads/.

These run in CI without network access or the raw ad copies (those stay local and are never committed),
so they check structure only. The full quote-back check is spikes/step4_check_fixtures.py, run locally.
"""
import json
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "ads").glob("*.json"))
REQUIRED = {
    "fixture_id", "source_name", "source_url", "original_doc_url", "fetched_at", "method", "raw_files",
    "raw_sha256", "fields", "checks", "completeness", "status_under_5a", "status_reason",
}
STATUSES = {"auto_verified", "needs_confirmation", "needs_upload", "closed"}


def test_fixtures_exist():
    assert FIXTURES, "no fixtures found"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_shape(path: Path):
    ad = json.loads(path.read_text(encoding="utf-8"))
    missing = REQUIRED - ad.keys()
    assert not missing, f"missing keys: {sorted(missing)}"
    assert ad["fixture_id"] == path.stem
    assert ad["source_url"].startswith("https://") or ad["source_url"].startswith("http://")
    assert ad["status_under_5a"] in STATUSES
    assert ad["raw_files"], "every fixture names the raw files it was extracted from"
    # Every filled field keeps the exact quote it came from (the quote-back rule).
    for name, field in ad["fields"].items():
        if field and field.get("value") not in (None, "", []):
            assert field.get("quote"), f"field {name} has a value but no quote"
