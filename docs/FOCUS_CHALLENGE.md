# Focus Challenge — implementation handoff, 19 November 2026

Shown to players as **Reaction Test** (Minigames tile, page title and start
button). Code, database and rules keep the name Focus Challenge.

The contributor confirmed teammate approval and requested the complete game.
R-M06–R-M09 in `docs/ontology/RULES.md` are the active implementation contract.
This branch includes the game, authoritative persistence and the scoring effect.
The contributor applied migrations 014/015 to shared Supabase on 19 November
2026. A fresh server client verified Focus status in all eight explicit QA
seasons: zero uploads, threshold zero and unlimited=true, including six older
snapshots without Focus rules. This confirms setup/status, not a completed
deployed game. Human phone difficulty calibration and deployed gameplay remain.
No shared game attempts or scores were created by that verification.

## Activation

1. Review this branch and migrations 014/015 with a teammate.
2. The Data owner applies 014 after 010, 011, `012_qa_minigames.sql` and
   `013_checkin_photo_privacy.sql`. Migration 014 is repeatable. Do not rerun
   `schema.sql` on an existing database. Fresh databases also need these
   feature migrations. Then apply `015_focus_test_replays.sql`. Both scripts
   are repeatable in this order; when 014 is already installed, apply only 015.
3. Merge the reviewed PR and deploy/restart with the same pinned requirements.
4. Select an **existing explicitly marked QA season** or create one with the
   Wednesday 08:00 test-season option. The frozen `test_mode` flag must be JSON
   boolean true; names alone do not enable QA. No new season or uploads are
   needed. Older QA snapshots use the fixed v1 Focus configuration, without
   modifying their saved rules. Older normal snapshots remain disabled.
5. In QA, start with zero uploads, fail and retry, then win and replay while
   the boost is active. QA permits unlimited sequential plays throughout an
   active season, even outside the weekly drink window. Normal seasons retain
   five/seven/nine unlocks, one win per evening and the scoring window.

No new dependency, public database privilege or credential is needed. A missing
migration shows a setup message. Existing Check-in/Chug Duel scoring remains
usable; a failed boost preview never determines the authoritative award.

## Player workflow

Open Minigames → Focus Challenge. The page shows the three tasks, next count
threshold and any active boost. Retakes/retries/rejected posts do not count;
the player's shared duel entry does. Deleted photos leave accepted entries
and their count intact. After a failed attempt the normal-season threshold rises
by two. QA instead shows a test-mode label and immediate Start, without progress
or a nightly win block. Finish the result screen with Back to games, then reopen
Focus to replay. A missing migration 015 shows an explicit setup message.

Start opens a full-screen board. Start reaction begins one unpredictable signal
after a 3.5–6.5 second wait; pass within 220 ms. Start memory begins a one-second
lead-in and seven highlighted positions on a 3x3 grid, followed by fifteen seconds
for input. Start precision opens twelve targets to tap within twelve seconds.
New attempts must pass all three stages before earning the boost. An early tap,
wrong memory answer or wrong precision target ends the attempt. Running games
from the older reaction-only release retain their previous rules.

Ready screens time out after thirty seconds; reaction responses after two.
The entire attempt lasts at most three minutes, and ends sooner at 06:00,
scoring closure (normal seasons) or season end. Closing/reloading does not reset it or generate
new content. Memory/reaction steps and precision checkpoints are persisted.
The browser caches pending evidence to recover a lost reply. Two seconds of
server delivery grace accommodates transport; task timers do not gain time.

On a saved win, an automatic x1.5 effect lasts up to sixty minutes, bounded by
scoring/season closure. It can cross 06:00 and never stacks. An old evening's
unexpired boost prevents starting another Focus attempt until expiry. There
is one successful reward per member/lobby evening, independently of Chug roles.
Active Focus and started Chug games cannot overlap for the same member.
The QA exception removes count/win/active-boost gates. Further QA wins refresh
expiry to sixty minutes from that win, capped at season end, never stack factors
or accumulate hours. QA still requires an active season, keeps the 06:00 attempt
cutoff and all task deadlines. Ordinary drink scoring keeps its weekly window.

Only ordinary Check-in awards are boosted, including matched territory points.
The previous owner's 25% uses that boosted award. A 1-point drink becomes 1.5;
its owner income is exactly 0.375. A corrected 3-point drink becomes 4.5 with
1.125 owner income. Self/team-self income remains zero. In teams, only the
successful player's entries receive the boost. Chug Duel sources/transfers do
not receive it, even when its winner currently has a Focus effect.

## Code and data

- `core/focus_challenge.py`: frozen per-season configuration, availability and
  bounded component-message validation. `new_rules()` copies the configuration
  into new seasons. SQL reads that saved snapshot for thresholds and timing.
- `components/focus_challenge/`: accessible touch/keyboard controls, monotonic
  timing, server-anchored deadlines, pending-event recovery and precision prefix
  checkpoints. `logic.js` has pure helpers exercised by the Node test.
- `focus_challenge_component.py`, `focus_challenge_ui.py`, `minigames_ui.py`:
  authenticated page integration, progress, start/recovery, board and results.
  Three-second polling preserves a keyed component; it does not restart clocks.
- `data/db.py`: thin RPC wrappers and numeric row conversion. Clients send
  action evidence and expected revision, never a trusted win or points factor.
- `014_focus_challenge.sql`: private attempts, server random material,
  membership checks, lobby transaction locks, idempotent start/results, stage
  validation, deadlines, one-running/one-win indexes and immutable boost source.
- `015_focus_test_replays.sql`: explicit-QA detection, effective configuration
  for existing QA snapshots, server-derived attempt flag and a normal-only
  one-win index. RPCs retain membership checks and a single running game. New
  QA wins refresh one boost; the immutable source still records the actual win.
- `DrinkEntry.focus_attempt_id`: the source grant at check-in receipt time.
  Corrections keep it; replay recomputes the corrected award with that original
  multiplier after expiry. Neither correction nor replay compounds multipliers.
- `points_awarded` and `owner_bonus_quarters` become exact SQL numeric values.
  Existing quarter-unit readers remain compatible; a half-quarter means 0.125
  points. Python uses only binary-exact integer/half-unit values here. The
  common formatter retains three decimals. No historical award is rescaled.
- Check-in previews, saved receipts, photo history, leaderboard and territory
  replay use those awards. Capture-gap hints accommodate half-point awards once
  Focus entries are present. Photo deletion/retention and Chug transfers remain
  unchanged.

## Security and limits

Public/anon/authenticated roles cannot read attempts or execute game RPCs.
Only the existing trusted server role can call them; every public game RPC
also verifies the supplied player's current membership. Private challenge
material is persisted once per attempt, using cryptographic UUID entropy with
bounded rejection sampling, never a calendar/player/attempt-number seed.
Only the current stage's required content is sent to the component. Memory
answers are omitted from later snapshots once its presentation ends.

Timers and taps still originate in a browser and remain tamperable. Server
validation prevents unauthorized awards, skipped phases, duplicate rewards
and refresh-based rerolls; it cannot prove that a human physically made each
tap. This is the class project's trust-based skill game, not a medical test,
automated cheating detector or assessment of fitness to ride/drive. No health
label, photo, microphone, motion-sensor data or exact GPS is collected by Focus.
Attempt records are part of competition history; the project's broader account
history/retention policy remains applicable.

## Verification

- Python: `python -m pytest -q`. Development runs additionally block live
  Supabase client creation. The latest full regression suite passed 652 tests. Focus tests cover configuration freezing, safe
  bridge messages, exact fractional replay/corrections, team scope, errors,
  unlock UI, restart recovery and keeping older seasons disabled.
- Browser state machine: `node tests/focus_component.cjs` checks reaction
  timing/early taps, unchanged clocks during polling/reload, memory playback,
  precision prefixes, misses/timeouts and terminal results without new rewards.
- Isolated PostgreSQL: `node tests/focus_postgres.cjs PATH_TO_PGLITE_INDEX_CJS`.
  Uses optional PGlite already used by the project; never shared Supabase.
  Covers migration repeat, real service-role grants and anonymous denial,
  separate identities, five/seven/nine gates, persisted random material,
  stale/invalid actions, all stages, one reward, corrections, exact owner
  income, Chug exclusion, expiry, midnight/06:00 carry-over, timeout, team scope,
  old snapshots and reopening a saved running attempt/database after restart.
  Controlled entropy is injected only in this isolated test to avoid random
  flaky assertions; production uses cryptographic entropy.
- QA replay update: full Python suite **652 passed** with live client creation
  blocked; Focus/Chug UI subset **56 passed**. The PostgreSQL checks also cover
  existing QA snapshots, zero-upload start, retry after failure, multiple wins,
  nonstacking 1.5 awards, restart, repeat migration and strict boolean QA flags.
  QA games outside the weekly window remain playable, while drink submissions
  and expired-season games are rejected. The component tests check QA result text.
  A browser opened an existing QA snapshot with zero entries, started the actual
  game and returned to an enabled Start after the attempt ended.
- Existing `tests/scoring_postgres.cjs` and `tests/chug_duel_postgres.cjs`
  regression suites passed after the shared rule/default changes.
- A 390x844 browser completed reaction, observed and repeated the actual
  randomized memory flashes, completed precision and saw the saved win through
  the real component and RPCs against isolated PostgreSQL with five synthetic
  accepted entries. The saved reaction times were 193/114/171/111/215 ms; the twelve precision taps finished at 3709 ms. This proves the automated software flow, not human difficulty balance.

Still check after deployment: immediate QA
play with zero uploads and repeated wins, real iPhone/Android timing and target usability,
switch-away/reconnect on mobile networks, an actual boosted check-in and its
territory/leaderboard/history and teammate review.

## Zero-threshold UI fix — 19 November 2026

A deployed test-season page raised ZeroDivisionError while drawing unlock
progress after migration 015 returned threshold zero. Its traceback referenced
an earlier function layout, suggesting an imported screen or fragment had
survived deployment. Reboot the Cloud app and reload the browser after merging
this fix to replace old running functions. No additional SQL is required.

The screen now uses the authoritative status response for QA presentation,
so stale page season metadata cannot route a zero QA threshold through the
normal progress calculation. Nonpositive, missing or invalid normal thresholds
show a reload error without starting a game. The server still enforces every
start and award. Streamlit regression tests reproduce the zero-division failure
before the fix and verify stale metadata, normal invalid values, QA replay and
normal unlock behavior after it.
Verification: `python -m pytest tests/test_focus_ui.py tests/test_focus_challenge.py
tests/test_chug_duel_ui.py -q --tb=short` passed all 61 tests. Deployment/reboot
and a completed game on the public URL remain to verify.

## Integration with photo sharing — 19 November 2026

The latest main adds default-OFF account photo sharing, team consent and
attributed photo frames. This branch keeps those access checks and frames,
while retaining Focus source labels and exact fractional award details.
R5 keeps Focus eighth-point income; R6/R-PH01 keep the stricter photo policy.
Privacy migration 013 is already applied to the shared project. Focus's new
migration is numbered 014 to avoid colliding with that deployed migration.
Its SQL behavior is unchanged; if an earlier Focus 013 script was already
applied, 014 can still be applied safely because it is repeatable.


## PR #64 conflict resolution: three-stage flow restored

The contributor explicitly selected one reaction within 220 ms, followed by
Memory and Precision, instead of main's reaction-only three-try game. The full
three-stage component and its DOM are restored together; the compact main page,
QA zero-upload fix, latest navigation and other teammates' work stay intact.

Apply `021_focus_three_stage_flow.sql` after 015, and after 018/019/020 if those
older changes are installed. It includes the optional 017 attempt-config setup,
so new installations do not need to apply 017 separately. Always apply 021 last.
No season snapshot, saved result or existing point award is rewritten.
Already-running reaction-only games retain their rules and false-start retry;
new games use one 220 ms reaction, a Start memory handoff with a one-second
lead-in, seven memory answers, then Start precision and twelve targets.
The reward is granted only after all three stages. QA/normal unlocks, score
correction provenance, owner income and nonstacking boost behavior are unchanged.

Migration 021 was installed on the shared project on 19 November 2026, after
PR #64 merged. Database checks confirmed the attempt config column, one reaction,
the 220 ms threshold and flow version 2. Live status RPC checks confirmed all
nine populated explicit test seasons still permit zero-upload unlimited play.
Refresh the app and start a new attempt to use the three-stage rules; an attempt
already running before installation intentionally retains its previous rules.
Earlier reaction-only descriptions in this handoff are historical; R-M07/R-M08
and this section define the selected final behavior after migration 021.

Resolution verification: all 938 Python tests passed. The component checks now
also assert that every referenced DOM node exists. The PostgreSQL suite applies
the full migration order and verifies 220/221 ms, every stage, rewards, QA/normal
gates, migration repeat, restart and preservation of an already-running 020 game.
A real browser completed one fast reaction, reloaded at Start memory, observed
and repeated all seven flashes, tapped twelve precision targets and received
the saved boost against isolated PostgreSQL. That complete browser playthrough
used isolated PostgreSQL; the later shared-project installation and status checks
above do not replace a full deployed phone playthrough.
