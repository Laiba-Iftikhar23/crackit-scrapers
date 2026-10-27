# Ad fixtures (Phase 0 step 4)

22 real government job ads, fetched 23–24 Oct 2026 from official sources, for testing the parsers, the auto-verifier (`docs/architecture.md` §5a in the private `crackit-app` repo) and the eligibility engine.

- **Extraction is manual** (done by Claude during Phase 0, not by the production Gemini extractor). Every filled field has the exact `quote` it came from; a field the source doesn't state is `null` with a `note`. Nothing is guessed.
- **Raw copies are NOT here.** The HTML/PDF/image files and OCR text live in `spikes/data/step4/` (gitignored). `raw_files` and `raw_sha256` record what each fixture was read from. Official documents are never committed or re-hosted.
- `checks`, `completeness`, `status_under_5a` and `status_reason` are written by `spikes/step4_check_fixtures.py` (quote-back against the raw text, a regex parse check, sanity rules).
- OCR text (`*.ocr.txt`) was made on-device with macOS Vision.
- Closing dates have passed for some ads since the fetch. `currently_open_at_fetch` says whether the ad was open when fetched; `pts_1` and `pts_2` were already closed but still listed.

## Fields

`org`, `post_title`, `bps`, `vacancies`, `age_limit` (`{min, max}`), `qualification`, `domicile_quota`, `gender`, `experience`, `test_service`, `last_date` (ISO date), `ad_no`.

Each is `{value, quote, from, note?, also_from?, conflict?}`:
- `quote` is a string, or a list of fragments when the source's layout splits the text.
- `also_from` holds the same fact in another file (a second source).
- `conflict` lists values from sources that disagree (e.g. NTS portal vs the employer's ad). The field value stays `null`.

Key fields for §5a: `post_title`, `last_date`, `bps` (not for armed forces), `age_limit`, `qualification`.
