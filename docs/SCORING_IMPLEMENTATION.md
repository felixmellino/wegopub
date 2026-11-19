# Scoring v1: implementation and Data handoff

Implemented on the `Scoring` branch following the contributor's instruction on
17 November 2026. Teammate review, merge and shared-project migration remain
deployment steps. The earlier three-page PDF is a historical review snapshot;
the current contract is [SCORING_V1.md](ontology/SCORING_V1.md).

## Apply the database change once per shared project

Review/back up the existing database and confirm migrations 001-004 and the
photo-storage setup are already applied. Run
[`005_scoring_v1.sql`](../migrations/005_scoring_v1.sql) in the Supabase SQL
editor. Do not rerun `schema.sql` on an existing project. New projects apply
`schema.sql`, photo setup and migration 005 in that order. Migration 005 can
be run again safely; it does not delete old entries or re-score old seasons.

`006_friendships.sql`, merged from the Identity block, is a separate migration
for Profile friends. It was previously named `005_friendships.sql`; only the filename changed.
Do not rerun it if it was already applied under that name. Existing databases need the friendship migration as well
for that feature. It is already included in `schema.sql` for fresh databases.

Keep the server service-role credential in local/deployment secrets. The new
functions and revision table deny public/anonymous clients. Migration 005 adds:

- frozen timezone, rule version and complete rules JSON on each season;
- selection size, version, stable event order, owner-income recipient and
  integer quarter-point income on entries;
- correction revision counters, timestamps and an audit table;
- transaction functions for season creation, acceptance and correction/replay.

Owner IDs are derived from existing accepted membership rows. No second
membership foreign key is added, so the original PostgREST relationship stays
unambiguous for older app versions. The updated photo query also names its
source membership relationship explicitly.

## Existing and new seasons

Existing rows default to `legacy`. Their entries, original points and scoring
flow are retained. Existing competitions are not silently upgraded. A legacy
season containing entries cannot be converted to v1 through a season update.

New lobbies start v1 through `start_scoring_season`. Once a lobby's existing
season has ended, a current member can start its next season from the Lobby
page. No overlapping active/future season is created by that RPC. New season
IDs naturally produce fresh standings and unclaimed territories. Existing
history remains viewable through the season picker. The existing duration
choices remain 7, 30 and 91 elapsed days; calendar-month semantics are still a
team decision for a later revision.

Until host/admin roles are defined, any current lobby member can start the
next season after the last one ends. Nobody can change the settings or dates
of an already created v1 season through an update. The timezone selector uses
named IANA zones; `tzdata` is explicitly pinned for Windows installs.

## How it works

`core/scoring_v1.py` holds the new table, volumes, rule snapshot, clock-window
logic, cooldown/correction helpers and pure replay. The app snapshots the
rules when a season starts. SQL reads that snapshot; it does not maintain a
second hard-coded point table. Both base points and UI volume labels use the
snapshot. Future scoring changes must preserve existing snapshots and have
an explicit version/rollout decision.

The acceptance RPC checks the actor's membership, season, selection, verified
location result, photo path, weekly window and shared cooldown. It generates
the authoritative submission time when the scoring request reaches the
database. The UI clock/preview is advisory: time is checked again after the
photo upload, so pressing Submit before closing does not reserve eligibility.

Writes take a transaction-scoped advisory lock for the lobby. Entry identity
recovers uncertain saves. The database assigns a stable event order under
that lock. This order, rather than display-rounded timestamps, determines
ownership when requests coincide. New entry and bonus writes commit together.

Replay awards the drinker their base points, pays 25% to the previous owner
when it is another member, then updates territory ownership. The owner bonus
is stored in quarters: base award 3 produces 3 quarters, or 0.75 points.
Standings use the same pure replay and precise integer accounting. For two
recipients reaching a season tie in one event, preserve the previously higher
ranked owner; distinct events use the earliest reaching order.

Only the author can correct a v1 entry. Corrections close at original
submission +120 seconds, exclusive, and at season end. A correction can finish
after the weekly Sunday cutoff if it is otherwise timely and the season is
still active. The entry's time/location/photo stay unchanged. The RPC records
the before/after selection, increments its revision and replays the entire
affected season in original event order. Updating all source rows and linked
income in one transaction prevents partial writes. Retrying an already saved
correction recovers its result, even after its deadline; a different stale
revision is rejected.

History shows receipt/submission time in the season timezone, drink/size,
base awards, owner-income recipient and correction audit. Its selectbox holds
only entry IDs so fresh values appear immediately after a correction. Photo
deletion/expiry does not remove points or owner income.

## Verification

The normal tests use no live credentials or shared records:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Local verification on 17 November 2026: the complete suite passed **215 tests**
(the run additionally blocked unmocked database connections). The PostgreSQL
harness passed against migration 005 applied twice, including persisted results
after closing/reopening its isolated database. Streamlit's localhost startup
and health endpoint passed. The dependency audit checked 70 installed packages
and reported no known advisories. `git diff --check` and local documentation
link checks passed. These are local results, not deployment or live Supabase
verification.

After integrating the latest `main` (including Profile friends and removal of
password recovery), the combined suite passed **231 tests**. The verification
blocked unmocked Supabase client creation, preserving the real HTTPS validation
test and leaving the shared database untouched. The PostgreSQL harness also
passed against the combined fresh schema, with scoring migration repeat and
saved state after restart. The four documentation conflicts were reconciled
without dropping the Identity block's features or decided season choices.

The additional PostgreSQL harness uses an isolated PGlite database. Install
PGlite as a temporary development tool, not an app runtime dependency:

```powershell
npm install --no-save --prefix .venv/scoring-tools @electric-sql/pglite@0.3.14
$env:SCORING_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
node tests/scoring_postgres.cjs .venv/scoring-tools/node_modules/@electric-sql/pglite/dist/index.cjs
```

The harness creates test roles/tables, applies the real migration twice and
substitutes a controlled test clock only inside its isolated SQL text. The
production RPC accepts no client-supplied scoring/deadline clock. It compares
SQL awards against Python replay, covers migration/legacy preservation,
quarter-point income, captures, weekly and season cutoffs, exact cooldown
boundaries, correction audit/conflicts, duplicate recovery, protected access,
fresh seasons and reopening the on-disk database after restart.

UI tests exercise the real Streamlit controls with isolated data services:
category/size previews, shot size omission, mixed labels, closed-window and
cooldown forms, lost-save recovery, correction and a fresh history session,
timezone selection and revoked membership. These do not replace a real
Supabase/PostgREST integration test or a multi-connection load test.

## Live checks still required

The shared database has not been modified by this implementation task. After
the Data teammate applies migration 005 and confirms photo storage setup:

1. Create a test lobby/season, confirm its timezone/rules persist after restart.
2. During its legitimate scoring window, submit with valid location evidence,
   reopen the photo and check both score accounts and the owner recipient.
3. Try two simultaneous sessions, an exact two-minute retry and a lost reply.
   Confirm one entry and one income award per source capture.
4. Correct an entry within two minutes and verify downstream ownership,
   recipient changes, audit and persisted results after an app restart.
5. Verify public clients cannot call scoring functions or read revisions.
6. Delete/expire a photo, preserving scores, and verify scheduled cleanup.

The Location block's browser button is now connected to the camera-first UI.
It supplies the phone position and accuracy; manual inputs are removed.
R-L01–R-L03 select phone-only GPS, a 50 m accuracy limit and point-based
territory matching. Photo GPS is ignored. Phone permission, real camera capture
and live Supabase integration still need device testing; automated checks use
isolated browser-component responses and never request a real location. Friend
confirmation, minigame multipliers, membership leaving/absence rules and
post-deadline moderation have not been added by this scoring change.
