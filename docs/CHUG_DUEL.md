# Chug Duel implementation handoff

Contributor-authorised rules, 18 November 2026, recorded in RULES.md
R-M01–R-M05. Migrations 011 and 012 were applied to the team's shared Supabase project
on 18 November 2026 with explicit contributor authorization. Live schema/RPC
and read-backed page checks passed; real two-phone verification remains
pending. The earlier minigame proposal is historical.

## Player workflow

Minigames is the Games tab, immediately right of the plus in the five-tab bottom bar.
Its catalogue lists games in one list; tap the Chug Duel row to open the
existing duel controls. All games returns to the catalogue without cancelling
an invitation or spending an allowance. Focus Challenge now opens separately in new seasons enabled by its frozen
rules; its boost never applies to Chug Duel entries or transfers. The host's running full-screen
board still resumes automatically before catalogue navigation.
Select any eligible other member of the current lobby, choose the common
drink/size, and send an invitation. The other player accepts on their own
device. The host takes one fresh photo of both drinks; their current GPS is
used for both entries. The same normal scoring window, season dates, two-minute
cooldown for each member and location acceptance rules apply. No extra
time-since-first-post or post-count gate applies to this game.

The host saves the shared check-in, then both players use the split screen on
the host's device. Each half has a separate Ready action. The server arms a
three-second countdown after both are ready; the first subsequent browser
pointer/keyboard event locks the outcome before a network round trip. Only the
host can submit the winner. Participants trust each other about physical
completion; neither the camera nor the app proves a drink was emptied.

The host's playing board fills the app viewport and disables page scrolling
and bottom navigation. The same component stays mounted from Ready through
the visible 3/2/1 countdown, GO and the saved result. A compact × can end the
game without a winner; Back to Minigames dismisses an ended/result board and
restores navigation. Receiving players continue to use their normal page.

Example outside all territories: two 3-point drinks give 3/3 at start, then
6/0 on a recorded win. A started abort keeps 3/3. Territory-linked entries
still give each competitor 3 territory points. Owner income is calculated
normally in entry acceptance order and is never transferred by the duel.
Thus a loser can still have owner income in addition to the zero base award.

## Code and persistence

- `core/chug_duel.py`: 06:00 calendar-night identity (season timezone), separate
  role allowances, pair validation, component message validation and errors.
- `minigames_ui.py` / `pages/7_Minigames.py`: invite, accept/decline, capture,
  readiness, board, result, abort and three-second polling. Identity and lobby
  checks run before rendering; every mutation checks again on the server.
  The host's started duel is rendered first in a stable `chug_duel_stage`
  container, replacing the lobby list while playing. Its ID stays focused
  through completion/abort until explicit dismissal. `assets/minigames.css`
  pins the stage/iframe to the viewport and disables surrounding scrolling
  and navigation only while that stage exists. Server state still determines
  results and expiry; this presentation change needs no database migration.
- `components/chug_duel/index.html` / `chug_duel_component.py`: browser timing,
  touch halves and keyboard access. Names use textContent; no public text is
  inserted as HTML. Countdown uses a server-time anchor and a monotonic
  browser clock, so phone wall-clock settings do not bypass it.
  The local countdown deadline is set once per server `play_at`, and never
  reset by polling. A live Ready acknowledgement shows a full three seconds,
  even if part of the server's minimum delay elapsed during the round trip.
  Reopening an already armed game uses its saved server deadline.
- `data/db.py`: membership-checked, metadata-stripped shared capture and RPCs.
  No exact GPS is stored or passed to SQL. One capture produces two private
  JPEG copies at the existing entry-owned paths. Each player can delete their
  own copy under existing R7; the other's copy has its own lifecycle. Both
  expire with the same season's normal photo-retention rules. Failed uploads
  create no scores; unreferenced files use the existing orphan cleanup.
- `migrations/011_chug_duel.sql`: authoritative server receipt clock, lobby
  transaction lock shared with scoring/team membership, role-specific unique
  indexes, participant authorization, phase expiry and atomic two-entry start.
  Public/anon/authenticated cannot access the table or call its RPCs.
- `DrinkEntry.duel_id`: links the two normal source entries. Their agreed
  drink/size cannot be corrected separately (both Python and SQL enforce this).
- On completion only the losing source stores `duel_transfer_to` (the saved
  winning member/team account) and `duel_transfer_order` (a new position in the
  existing scoring sequence). Replay credits/debits that base award at result
  time, preserving every original territory event and owner-income award.
  Terminal duel results are immutable and retries return the saved result.
  Same-result simultaneous ties preserve the previously higher-ranked account.
- `core/scoring_v1.py` replays base and transfer events together. Existing
  leaderboard/map/lobby callers receive the same DrinkEntry list interface.
  Normal corrections replay ownership/income without removing duel transfers.
  Photo history displays the resulting 6/0 season awards and normal territory
  awards. Legacy records and season snapshots are not rewritten.

The old `core/minigames.py` weekly placeholder and its tests remain for legacy
code; Chug Duel does not call it. This is the explicit exception to the earlier
one-game/items-only design. Focus Challenge is implemented separately under R-M06–R-M09; see FOCUS_CHALLENGE.md.

## Boundary defaults

Invitations expire after ten minutes. Accepted setup has ten minutes to start,
and a started game has ten minutes to finish. A phase also ends at the 06:00
rollover, scoring-window close or season end, whichever comes first. Pending
expiry consumes nothing. Accepted cancellation/expiry frees both reserved
roles; started expiry/abort consumes the host's outgoing and guest's incoming
roles while retaining both normal drink awards. Reconnecting can resume a
started game until expiry. One pending outgoing invitation and one
accepted/started game per member avoid overlapping physical games. A player
can subsequently play their opposite role that evening. A different lobby
has independent allowances. Team membership is checked again on start;
scored entries then retain the existing immutable team identities.

QA replay exception (R-M02): the frozen boolean `scoring_rules.test_mode=true`
removes outgoing/incoming nightly count limits. Both indicators read Unlimited;
completed/aborted games permit another match in the same roles and night.
Migration 012 derives a `chug_duels.test_mode` flag from the actual season,
backfills existing attempts and exempts only those rows from the role-specific
unique indexes. Caller-supplied flags are overwritten; duel identity is frozen.
The helper still rejects simultaneous active games and one pending outgoing
invitation remains the limit. Existing normal seasons retain their limits.
Photo/GPS evidence, window/end boundaries, two-minute cooldown and all scoring
and idempotency rules still apply; test points remain in their own lobby.

## Verification

Unlimited QA follow-up, 18 November 2026: full Python suite **516 passed**;
the isolated PostgreSQL suite verified migration 012 twice, backfilling older
QA attempts, repeat games in the same roles/night after wins and aborts,
exactly-once transfers, cooldowns, non-overlap, restart persistence, and normal
limits even with a forged test flag. The two-session browser suite repeated
challenge/accept/play after a win, aborted a second game and challenged again;
both indicators stayed Unlimited. Migration 012 was applied to shared Supabase
on the same day. Live read-only checks confirmed both existing finished QA
games were replay-eligible, saved flags matched frozen season rules, and the
actual page rendered Unlimited with a new challenge available using live
read services. Record counts and stored point fields matched the pre-migration
baseline. No live game or score was created by these checks. The new Python/UI
changes still require commit/merge/deployment to update the hosted app.

Full-screen UI follow-up, 18 November 2026: fixed the reported jump after both
Ready taps by keeping the host board in a stable, fixed viewport stage through
the result. Full Python suite **508 passed**. The browser suite verified the
same iframe at the same viewport coordinates through Ready, 3/2/1, GO and
saved winner; wheel scrolling, portrait/landscape resizing, restored navigation,
keyboard finish, an ended game and resuming an already armed game were checked.
This UI follow-up is local and awaits commit/deployment; no new migration or
live state change is required. Real phone browser chrome and touch behavior
remain part of the device check below.

Verified locally on 18 November 2026: full Python suite **507 passed**;
isolated PGlite integration **passed**, including disk reopen; actual browser
board and two independent synthetic Streamlit sessions **passed**. The browser
workflow used the real camera component with a fake video device, synthetic
GPS/services, and 390 px mobile plus desktop screenshots. Real phone hardware
and the shared Supabase deployment were not used. `git diff --check` passed.

Live setup follow-up, 18 November 2026: the deployed page's setup error was
traced to missing `chug_duels` and RPCs. Applied the unchanged migration 011
through the authenticated Supabase SQL Editor, after confirming the dashboard
project matched the app's configured database. Supabase returned success.
All four app-facing RPCs were reachable and rejected an unauthorized dummy
actor. A valid existing membership could read its duel list. The actual
Minigames page rendered with live read services in AppTest, using a supplied
valid membership context: no setup errors, both allowances available. This
was not a browser login or a completed live game. Existing counts of players,
memberships, seasons, teams and drink entries were unchanged; no test duel,
account or score was created. Real phone camera/GPS and a full two-device
game remain the final deployment checks.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Targeted workflows: `tests/test_chug_duel.py`, `tests/test_chug_duel_db.py`,
`tests/test_chug_duel_ui.py`, `tests/test_app_navigation.py`, plus existing
scoring, team, photo and standings tests. UI tests use independent AppTest
sessions and isolated services; they do not connect to Supabase.

Optional database integration uses Node and `@electric-sql/pglite@0.3.14`
installed under ignored `.venv/chug-test`, without a new production dependency:

```powershell
$env:SCORING_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
node tests/chug_duel_postgres.cjs .venv/chug-test/node_modules/@electric-sql/pglite
```

It verifies migration repeatability, authorization, role limits, competing
accepts, atomic cooldown rollback, countdown enforcement, idempotent 6/0
transfer, team identities, expiry, aborts, midnight/06:00 and disk-backed
PostgreSQL reopen persistence. The clock substitution exists only in the
isolated test migration copy. PGlite queues queries in one engine; this is not
a multi-connection load test of hosted PostgreSQL.

Optional browser check with installed Playwright/Chromium or Edge:

```powershell
node tests/chug_duel_browser.cjs
```

This exercises the actual HTML board (readiness, early taps, countdown,
first-tap lock and escaped names). `CHUG_QA_URL` can target an explicitly
synthetic localhost Streamlit fixture for a two-browser workflow and mobile
screenshots. It refuses remote hosts. QA images stay under ignored `.venv`.

## Deployment and remaining phone checks

For a new database, apply `migrations/011_chug_duel.sql` after 010, then
`migrations/012_qa_minigames.sql` for unlimited QA replays through the
team's normal database migration process. The shared project already received
011 and 012 on 18 November 2026; the original feature was merged through PR #40.
Deploy the QA UI update so the hosted page also exposes replay actions. With two real
accounts on phones, verify invitation updates, permissions for the common
camera/GPS, touch halves/countdown, both histories and the leaderboard. Repeat
after a Streamlit restart; check cancellation and a started abort, then
confirm the separate outgoing/incoming limits in a normal lobby and repeated
sequential replays in a QA lobby. For true concurrency, use two
database connections to race acceptance/start/result against the same lobby.

## Catalogue verification — 19 November 2026

`python -m pytest -q` (through pytest.main with live client creation blocked)
passed 587 tests. Focused Chug Duel UI/core and legacy minigame checks passed
32 tests. Synthetic browser verification covered desktop/390px phone cards,
opening the existing Chug Duel form and returning to the catalogue. No live
records were changed; that catalogue-only layout required no migration.
Focus Challenge was subsequently implemented under R-M06–R-M09; its separate
migration 014 and activation steps are in `docs/FOCUS_CHALLENGE.md`.
