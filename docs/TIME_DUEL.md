# Time Duel implementation and handoff

Implemented locally on `minigametimestopper`, 19 November 2026. Rules are in
[ontology/TIME_DUEL.md](ontology/TIME_DUEL.md), referenced by R-M10. Migration 017 was applied to the shared WeGoPub database on 19 November 2026.
Teammate review and public app deployment remain pending.

## Invitation fix — 19 November 2026

On `timeduellFix`, invitations now appear above the Minigames tiles and inside
Time Duel. The sender gets the Pending Challenge invite box, a server-based
expiry countdown and Cancel. Multiple incoming invitations require a warning
and Confirm acceptance before selecting one. Acceptance resolves both players'
other Time Duel invitations atomically, then opens the normal Ready board.
Pending and accepted/running games block further outgoing challenges on the
server, including in QA and from separate tabs. Current pending invitations
are never hidden by the twenty-item terminal-history limit. The existing
ten-minute expiry and earlier scoring/night/season cutoffs remain in force.

Migration `021_time_duel_invitations.sql` was applied to the shared WeGoPub
database through the Supabase SQL Editor in Safari on 19 November 2026, with
explicit contributor authorization. It replaces three RPCs and preserves saved
games/rewards; it can be safely reapplied after 017. The editor reported success.
All six read-only verification checks passed: the stored bodies of `time_status`,
`invite_time_duel` and `time_action` match migration 021 exactly; the pending
invitation unique index exists; all three RPCs remain restricted to the service
role; the three-round, ten-minute-invitation and x1.25 gameplay configuration is
unchanged. The project identifier was checked against local app configuration.
The local full app now uses these updated database functions. Teammate review
and deployment of the UI changes from main are still needed for the public site.

Verification for this fix:

- `.venv/bin/python -m pytest -q`: **944 passed**.
- `PYTHONPATH=/private/tmp/time-duel-test-tools .venv/bin/python scripts/verify_time_duel.py`:
  synthetic normal/QA invitation delivery, same/opposite-target duplicates,
  retry identity, 599/600-second expiry, acceptance cleanup, active guards,
  simultaneous sends/acceptance, RPC permissions and actual database restart;
  existing round/scoring/reward regression checks retained.
- Three independent local browser sessions backed by disposable PostgreSQL:
  automatic delivery above tiles, sender pending box and disabled send, refresh
  recovery, multiple-invite confirmation, other sender released after decline,
  accepted duel and matching first-round target on both devices.

The browser fixture supports `TIME_DUEL_FIXTURE_PORT` (default 8781) so another
local fixture can remain running. Use the same value for the SQL bridge and
Streamlit process. Start from the catalogue and open Time Duel to send.

## Where it lives

- `core/time_duel.py`: component input validation and explainable outcome examples.
- `components/time_duel/index.html`: accessible Start/Stop phone board, monotonic
  timing, immediate local result, ordered retry queue, reload/visibility abandonment.
- `time_duel_component.py`, `time_duel_ui.py`: stable Streamlit component and lobby
  invitations, readiness, recent games and friendly service errors.
- `minigames_ui.py`, `assets/minigames.css`, `assets/games/time-duel.svg`: catalogue
  entry and phone layout.
- `migrations/017_time_duel.sql`: private tables, participant-scoped RPCs, server
  targets, first-result locks, shared minigame/membership guards, nightly role
  reservations and reward intervals. The lobby transaction lock serializes actions.
- `core/models.py`, `core/scoring_v1.py`, `data/db.py`: immutable Time Duel source
  and separate `time_bonus`; season standings and Quiz spendable balance include
  that bonus. Territory replay, owner income and lifetime points use the original
  award. Focus remains x1.5 with its existing broader effects, without stacking.
- Check-in preview/success and photo details show the correct season award.

The database is authoritative for winners/rewards. Browser intervals are bounded
trust-based evidence; this is not automated anti-cheat. Timing never waits for a
network response. Start and Stop events are queued in order, and the first saved
result cannot be replaced. Reloading a running clock sends an abandonment;
if disconnected, the server deadline enforces it when the game is next read.

## Run and verify

App and normal suite, from the repository root:

```sh
.venv/bin/python -m streamlit run app.py
.venv/bin/python -m pytest -q
```

SQL verification uses disposable PostgreSQL, synthetic users and no Supabase
credentials. Optional tools are outside app dependencies:

```sh
.venv/bin/python -m pip install --target /private/tmp/time-duel-test-tools \
  pgserver==0.1.4 'psycopg[binary]==3.2.13'
PYTHONPATH=/private/tmp/time-duel-test-tools .venv/bin/python scripts/verify_time_duel.py
```

The helper initializes its own database under `/private/tmp`, listens only on a
local Unix socket, and stops/deletes it afterwards. No existing server or database
is used. PostgreSQL requires permission to create local shared memory.

Two-browser verification, with Playwright installed as a development tool, uses
these commands in separate terminals:

```sh
PYTHONPATH=/private/tmp/time-duel-test-tools .venv/bin/python scripts/time_duel_browser_server.py
.venv/bin/python -m streamlit run tests/fixtures/time_browser_app.py \
  --server.address 127.0.0.1 --server.port 8782 --server.headless true \
  --browser.gatherUsageStats false
TIME_DUEL_BROWSER_CHANNEL=chrome node tests/time_duel_browser.cjs /absolute/path/to/playwright
```

Use an installed Chrome binary in fresh isolated profiles, or omit
`TIME_DUEL_BROWSER_CHANNEL` when Playwright's Chromium is installed. Stop both
servers afterwards with Ctrl+C. The browser fixture listens only on localhost
and overrides Time Duel database calls with the synthetic service.

Verified locally:

- Full Python suite: 900 passed (`.venv/bin/python -m pytest -q`).
- SQL: allowed/rejected/stale actions; hidden target/result payloads; first-result
  locks and concurrent acceptance; normal/QA allowances and 06:00 rollover; scoring-window gates; valid
  ties and incomplete ties; abandonment; exact reward/correction calculations;
  Focus precedence and expiry; territory/owner parity; team contribution;
  departed-member and browser-role denial; migration reapplication and actual
  database restart persistence.
- Two independent 390px Streamlit/Chrome sessions: invitations, readiness,
  matching target, hidden running timer, immediate result, opponent disclosure
  gate, three rounds, reward display, phone layout and reload abandonment.
- Result screenshot: `output/previews/time-duel-result.png` (local QA artifact).

## Activate and demonstrate

For a new database, apply `017_time_duel.sql` after `015_focus_test_replays.sql`,
`016_quiz_duel.sql` and `016_leave_lobby.sql`. The shared WeGoPub database already
has 017. Five SQL Editor checks passed for private tables, scoring fields, app
function permissions, active guards, and the three-round, one-hour x1.25 rules. Existing v1 seasons work immediately;
no frozen season snapshot is edited. Missing migration produces an actionable
setup message. Normal play requires the scoring window; explicit test seasons
allow sequential replays throughout the active season.

Teammate review is needed before merge because this integrates the shared entry
model and scoring replay. Follow the normal PR workflow; do not push to main.
After deployment, verify on two physical phones: invitation/acceptance, each
Start/Stop, screen lock/tab switch/reload, exact-once reward and boosted check-in,
then check that territory points and owner income remain unchanged. Phone timing
feel and real mobile network interruptions still need human verification.
