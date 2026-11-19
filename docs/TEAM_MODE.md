# Team mode handoff

The creator chooses Individual or Team in the Create lobby dialog. Team mode
adds team count, capacity and Random/Players choose. Open lobby shows team
cards; members join available teams, then click their own team name to rename
it or upload/take/remove its picture. Team totals decide season standings and
territory ownership. See R-TEAM01–R-TEAM05 in `ontology/RULES.md`.

## Shared database setup

Review and apply `migrations/010_team_lobbies.sql` after migrations 005 and 009
in the Supabase SQL editor before enabling team mode in the deployed code.
Do not recreate schema.sql. Existing individual lobbies and their scores are
preserved. No new bucket, secrets or runtime dependency is required. Pictures
are small sanitized JPEGs stored as base64 in the private team table, so they
are committed atomically with the name. The migration is repeatable.

The contributor explicitly authorised shared-database application on
18 November 2026. Migration 009 was missing; 009 and 010 were applied together
in one transaction through the open WeGoPub Supabase SQL editor. Teammate
review of the code and the normal pull-request workflow remain required.

## Where to look

- `core/models.py`, `core/teams.py`, `core/lobbies.py`: settings and identities.
- `core/scoring_v1.py`: one replay for team/individual totals, income and ties.
- `migrations/010_team_lobbies.sql`: automatic team creation, atomic capacity,
  random assignment, member-only edits, entry team snapshots and SQL replay.
- `data/db.py`: existing backward-compatible row readers and team API calls.
- `pages/2_Lobby.py`, `lobby_ui.py`, `lobby_forms_ui.py`, `team_ui.py`: overview, shared Create/Join dialogs, individual member/friend popup and team cards.
- Standings, Map, Check-in, photo history and Profile stats use team identity
  in team lobbies; check-in photo authorship remains individual.

## Verification

```bash
.venv/bin/python -m pytest -q
```

For isolated PostgreSQL checks (optional test tools, no production connection):

```bash
.venv/bin/python -m pip install --target /private/tmp/wegopub-lobby-sql-deps pgserver==0.1.4 'psycopg[binary]==3.2.13' fasteners==0.20
PYTHONPATH=/private/tmp/wegopub-lobby-sql-deps .venv/bin/python scripts/verify_team_lobbies.py
```

The SQL script checks migration repetition, old scores, team creation,
member-only editing, name uniqueness, picture persistence, unassigned scoring
rejection, team/self-income, correction replay parity with Python, capacity,
simultaneous joins, random balance, public-role denials and database restart.
It uses synthetic fixtures and a disposable local PostgreSQL cluster.

On a configured test deployment, use multiple accounts to create manual and
random lobbies. Verify full-team errors, late joining, team name/picture
visibility, camera permissions and a nonmember's denial. Score for two
teammates and a rival: verify combined leaderboard, team territory captures,
owner-income recipient in photo history, check-in ownership feedback and
Profile team stats. Try switching before and after scoring. Correct an entry
and compare Map/Leaderboard. Restart Streamlit and log in again to verify
saved settings, assignment, name, picture and scores.

Limits: uneven rosters can advantage larger teams; capacities are maxima.
There is no host role or team kick action. Existing profile picture privacy
continues to show initials for unrelated players. Minigames and their open
special-item rules are unchanged.

## Verification in this branch (18 November 2026)

The full pytest suite and the disposable PostgreSQL script passed locally.
A synthetic browser preview verified creation mode controls, team cards,
joining, member-only editing and a saved rename reflected on the lobby leader
card. PostgreSQL restart checks cover saved roster, names, pictures and
scores. The shared migration is now applied (see below). Real multi-account
camera/GPS verification remains pending.

## Shared Supabase application (18 November 2026)

Explicitly authorised by the contributor in this chat. The preflight confirmed
005 was installed, while 009 and 010 were missing. Both migration files were
run in one transaction with a 5-second lock timeout and 30-second statement
timeout. Supabase returned success. Twelve post-application checks passed:
009's guard, team table/functions/triggers, team-aware replay, preserved
individual lobbies/memberships, unchanged scoring and season records, and
server-only access with RLS enabled.

Before/after: 9 individual lobbies, 14 memberships, 7 seasons, 4 drink entries.
The season checksum and all pre-existing drink-entry fields matched exactly
(excluding newly added nullable team columns). No test records were inserted
into the shared database. The SQL editor remains on the all-passed summary.
Application code remains on TeamModeAddition until reviewed and merged; the
database update does not publish or merge the application code.

## PR 33 integration with current main

The conflict resolution retains main's clickable lobby cards, individual
member/friend popup, dismiss/cancel behavior and shared `lobby_forms_ui.py`.
Team mode is added to that shared Create dialog; the card router opens team
cards for team lobbies. Both detail types use `_opened_lobby_id`, while
`_lobby_dialog` selects only Create/Join, ensuring at most one dialog per run.
Successful creation/join opens the appropriate member or team popup; teams
retain retry setup, Close and View leaderboard.

Verification: `.venv/bin/python -m pytest -q` passed all 469 tests. Added
coverage checks team creation through the shared form, popup switching and
dismissal, team selection for navigation, and incomplete-team-lobby retry.
Synthetic browser checks confirm both individual member/friend controls and
team cards remain available after the merge. No scoring or database migration
changed in this integration.
