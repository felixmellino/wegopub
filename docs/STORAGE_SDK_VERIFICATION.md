# Storage SDK upgrade verification — 18 November 2026

The old `supabase==2.9.1` / `storage3==0.8.2` parser crashes when the
Storage bucket response includes `versioning_status`. Upgrade to
`supabase==2.34.1` on Python 3.11+. This branch starts from current main
and preserves the Data owner's original upgrade commit authorship.

## Completed

- Isolated Python 3.12.14 environment: `pip install -r requirements.txt`;
  full suite **305 passed**. The first cold run timed out on the Map AppTest;
  a complete repeat passed without increasing its timeout or changing assertions.
- `tests/test_storage_sdk.py` passes the bucket HTTP fixture through the
  actual installed SDK parser and the app's private-bucket guard. Both
  cases reproduce the exact `versioning_status` TypeError under the old SDK.
- HTTP Storage errors still inherit `storage3.utils.StorageException`;
  PostgREST errors still expose `APIError.message` and `.code`, and actual
  HTTP error parsing still reaches the app's scoring rejection translation.
  Existing `httpx.RequestError` handling remains valid; timeout/retry UI,
  Lobby, history, corrections and deletion tests run with the new packages.
  No application exception imports needed changing.
- `pip check`: no broken requirements. `pip-audit`: no known vulnerabilities
  after updating the isolated environment's pip from 25.0.1 to 26.3.
  This environment contains no setuptools package. Repeat audits on deployment.
- Shared project: private bucket and required photo/scoring columns confirmed;
  global cleanup **preview only** returned zero expired and zero unlinked files.
- Live synthetic JPEGs in a temporary QA lobby: upload, member view, reopen in
  a fresh Python process, outsider denial, non-owner deletion denial, and
  denial after removing the viewer's membership all passed.
- Owner deletion preserved entry counts and score totals. Exact 30-day access
  expiry passed with a controlled application clock against real saved rows.
- Cleanup was restricted to the QA lobby and its explicitly recorded UUID
  object paths. Preview, apply and a second apply passed: expired and abandoned
  photos removed; active photo and scores preserved. All QA objects and database
  records were then removed. No existing player records were changed.

These live checks exercised legacy storage fixtures, not a v1 check-in outside
the legitimate weekly scoring window. They prove storage integration and
fresh-process persistence; they do not replace a phone camera/GPS browser demo
and a valid v1 check-in during the scoring window.

## Daily cleanup activation

The user selected GitHub Actions. `.github/workflows/photo-cleanup.yml` runs
daily at 04:17 UTC on main and supports a manual preview (Apply defaults false).
Actions are pinned to official commit SHAs, repository permissions are read-only,
credentials reach only the cleanup step, and concurrent cleanups are serialized.

After teammate review and merge, a repository administrator must:

1. In Settings → Secrets and variables → Actions, privately set
   `PHOTO_CLEANUP_SUPABASE_URL` and `PHOTO_CLEANUP_SUPABASE_KEY` to the team's
   server endpoint and service-role credential. Never paste them into issues,
   PRs, logs or workflow source. This runner has privileged database access.
2. Open Actions → Private photo cleanup → Run workflow on main, leaving Apply
   false. Confirm the counts and a green run; then run once with Apply true.
3. Confirm the first scheduled run and enable workflow failure notifications.
   GitHub may delay schedules; public repository schedules may be disabled after
   60 days without repository activity. Monitor this rather than promising an
   exact physical-deletion time. App access expires independently at 30 days.
   See the [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Secrets and hosted workflow execution have **not** been configured or verified
in this task. No deployment URL or hosting control is currently recorded in
README. Teammate review, merge, deployment reinstall/restart and a real phone
smoke test remain outstanding.
