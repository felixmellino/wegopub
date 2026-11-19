# WeGoPub — Working Guide

How this codebase is organized, how it connects to `docs/ontology/`, how
the four building blocks are split, and exactly how to work on your piece
using Claude Code, even if you can't read code yourself. Read `AGENTS.md`
first for the short version of the team workflow rules; this file is the
full explanation behind them.

## The big picture

Think of the app like a restaurant.

- **`pages/` and `app.py`** are the dining room — what a player actually
  sees and clicks on. The waiter takes an order and brings back a plate;
  no cooking happens here.
- **`core/`** is the recipe book — it says exactly how things are made
  ("a beer is worth 5 points per unit", "a drink only counts Thursday noon
  to Sunday night"). It never touches the real database, it's just the
  written-down rules.
- **`data/db.py`** is the fridge and pantry — the actual data, stored so
  it's still there tomorrow. It's the only file allowed to open the fridge.
- **`tests/`** is a food inspector who checks every recipe against known
  cases, without needing a working kitchen — it proves the rules work
  correctly, with no real database needed.

Follow one real action through the kitchen: a player opens Check-in (the
waiter), submits a drink, the waiter asks the recipe book "is this
allowed?" (`core/checkins.py`), the recipe book checks the rules and says
yes or no, and if yes, the waiter stores it in the fridge (`data/db.py`).
Nobody in the dining room decides the rules; nobody in the recipe book
stores real data.

## `core/` — the rulebook

Every file here is plain Python with no screen code and no database code
in it — that's why `tests/` can check it instantly, with no internet
connection.

| File | What it means, in one sentence |
| --- | --- |
| `models.py` | Defines the "things" in the game — Player, Lobby, Territory, DrinkEntry, etc. — just their labels and fields, nothing else. |
| `constants.py` | Legacy scoring/window constants plus shared GPS, minigame and photo lifecycle settings. New scoring settings live together in `scoring_v1.py` and are snapshotted per season. |
| `auth.py` | Turns a PIN into a scrambled code so the real PIN is never stored, and checks a typed PIN against it at login. |
| `lobbies.py` | Creating a player, creating a lobby (with an invite code), joining a lobby, and setting up that lobby's season. |
| `game_window.py` | One job: "is this moment inside Thursday-noon-to-Sunday-evening?" Drinks only count inside that window. |
| `location.py` | Checks whether the phone's GPS reading is accurate enough (50 m) and which territory's drawn area it falls inside. |
| `scoring.py` | Preserves the historical beer/wine-unit and flat Shot/long-drink calculator for legacy seasons. |
| `scoring_v1.py` | The new fixed size table, frozen season rules, lobby-time window, cooldown/correction checks and exact quarter-point ownership replay. |
| `checkins.py` | The main gatekeeper: pulls together the window check, the location check, and the scoring to decide if a submitted drink is valid, and builds the record of it. |
| `territories.py` | Works out who currently owns each territory, replaying every drink in time order so that a tie always favors whoever got there first. |
| `leaderboard.py` | The same tie-breaking idea as territories, but for the whole season's ranking instead of one territory. |
| `minigames.py` | Legacy weekly-limit placeholder; Chug Duel does not use it. |
| `chug_duel.py` | Chug Duel's nightly outgoing/incoming allowances, eligible opponents and component messages; SQL enforces mutations atomically. |

## `data/db.py` — the fridge

One file. It's the only place in the whole app that opens a connection to
the real database (Supabase) and reads or writes a row. It converts
between a database row and the plain `core/models.py` objects, but
contains no rules of its own — if you want to know whether something is
*allowed*, that question always belongs in `core/`, never here.

## What you see on screen

| File | What it means |
| --- | --- |
| `app.py` | The very first screen. On purpose, it does almost nothing — just a welcome message — so it never becomes a file everyone has to edit at once. |
| `shared.py` | Helpers every screen reuses to verify the current account, lobby membership and season, or ask the player to sign in/pick a lobby. Page plumbing and fresh access checks; no game rules. |
| `pages/1_Profile.py` | Create an account (real name stays private, username is public) or log in with a username + PIN. |
| `pages/2_Lobby.py` | Create a new lobby (and pick how long the season runs), join an existing lobby with its invite code, or switch between lobbies you've already joined. |
| `pages/3_Check_in.py` | Camera opens automatically; take a photo, pick drink/size, review live location and submit. |
| `pages/4_Standings.py` | Shows the season leaderboard and, for each territory, who currently owns it. |

Every page follows the same shape: ask `data/db.py` for the data it needs,
hand it to one `core/` function to get an answer, and just display that
answer. If a page looks wrong, the bug is almost always in the `core/`
function it called, not in the page itself.

## The rest

| File / folder | What it means |
| --- | --- |
| `schema.sql` | The blueprint for the real database tables — run once inside Supabase to create them. |
| `requirements.txt` | The outside tools the app needs installed (Streamlit, Supabase, Pillow, pytest). |
| `tests/` | One file per `core/` file, same name, each proving that file's rules behave correctly. |
| `docs/ontology/` | The actual game design, written in plain English by the team — the source of truth the code is built from. |
| `AGENTS.md` | Course requirements, grading criteria, and the team's own workflow rules. |
| `README.md` | How to set up, run, and test the app locally, plus what's not built yet. |

## Design system (direction "Rush")

The look of the whole app lives in one place: `assets/theme.css` (colour,
type and shape tokens such as `--bg`, `--accent`, `--territory-yours`, plus
base styles for Streamlit's own widgets) and the `[theme]` block in
`.streamlit/config.toml`. `theme.py` loads it on every page through
`shared.require_login()`. Page styles in `assets/*.css` only use these
variables; never add hard-coded colours there. Rules: green/red/grey are
reserved for territory status, the cream accent is the action colour, and
the vintage red (`--brand`) appears only in the wordmark and the 1st-place
medal. Icons: the tab bar and menu lists use Phosphor SVGs from `assets/icons`
(MIT licence, `theme.icon_css` / `theme.menu_icons`); other buttons still use
Material Symbols (`:material/name:`). No emojis. Menus look like iPhone grouped
lists: wrap the buttons in `st.container(key="menu_list_<name>")`.

## How `docs/ontology/` connects to the code

`docs/ontology/` is the design, written first, in plain English. `core/`
(and the rest) is the implementation of it. The code should always match
the docs — if they disagree, that's a bug to fix, not a detail to shrug off.

| In `docs/ontology/` | Implemented in |
| --- | --- |
| `ENTITIES.md` (the "things" in the game) | `core/models.py` |
| `GAME.md` → Points | `core/scoring.py` |
| `GAME.md` → Territories, Ownership | `core/location.py`, `core/territories.py` |
| `RULES.md` R-R01 (tie rule) | `core/territories.py`'s `replay_leader` |
| `RULES.md` R-T01, R-T02 (territory set, no overlap) | `data/territories.geojson`, read by `data/territory_file.py` and checked by `core/territories.py`'s `parse_territories`; copied into the database by `shared.get_territories()`; overlap checked in `tests/test_territory_data.py` |
| `RULES.md` R-M01–R-M05 → Chug Duel | `core/chug_duel.py`, `core/scoring_v1.py`, migration 011, `minigames_ui.py` / `pages/7_Minigames.py` |
| `SCREENS.md` | `pages/*.py` |
| `OPEN_DECISIONS.md` items not yet decided (like D-01) | A placeholder that does nothing yet, e.g. `core/scoring.py`'s `apply_owner_modifier` — already wired in, waiting for the real rule |

**The rule going forward:** whenever the team decides something that was
open, or changes a rule, update the `docs/ontology/` file *and* the
matching `core/` file in the same change — never just one.

## Building blocks — four pieces to split

Each block is a vertical slice: its `core/` rule files, their tests, and
the one page that uses them. One person can own a block end-to-end and
explain all of it.

| Block | Owns these files | In plain words |
| --- | --- | --- |
| **A. Identity & Lobbies** | `core/auth.py`, `core/lobbies.py`, `core/game_window.py`, `pages/1_Profile.py`, `pages/2_Lobby.py` | Accounts, logging in, creating/joining lobbies, and the Thursday-to-Sunday time window. |
| **B. Location & Territories** | `core/location.py`, `core/territories.py`, `phone_location.py`, `map_ui.py`, `pages/5_Map.py` | The hardest, most technical block: matching GPS to a territory, and working out who owns each one. |
| **C. Drink Entries & Scoring** | `core/scoring.py`, `core/checkins.py`, `pages/3_Check_in.py` | The biggest rulebook: how many points a drink is worth, and all the reasons a check-in can be accepted or rejected. |
| **D. Standings & Data layer** | `core/leaderboard.py`, `data/db.py`, `schema.sql`, the real Supabase project, `pages/4_Standings.py` | The season ranking, the one file that talks to the database, and actually setting up the live database. |

Chug Duel is now implemented across the shared scoring/data boundary; its
rules, ownership and verification handoff are in [CHUG_DUEL.md](CHUG_DUEL.md).
Other minigames remain future work after the core workflows are stable.

Everyone should still read `core/models.py` first, since it's the short
file that defines the "things" every other block works with.

## How decisions get made without blocking everyone

Full team approval for every small decision isn't realistic when working
individually. The default is to decide and announce, not decide and ask:

1. Decide it.
2. Build it.
3. Write it into `docs/ontology/`.
4. Post one line in the group chat — a notice, not a request for
   permission: "Decided: invite codes are 6 characters. See `RULES.md`."
5. Open your PR as normal.

**Ask the team first, only when your change does one of these three
things** — otherwise just announce it:
- Changes a field or type on something shared (`Player`, `LobbyMembership`,
  `Season`, `Territory`, etc.)
- Changes the behavior of a function another block already calls
  (`is_in_game_window`, `replay_leader`, `evaluate_location`, etc.)
- Contradicts something already written as *decided* (not just open) in
  the ontology

Your pull request is the real safety net: a teammate sees the code change
and the ontology change together before it reaches the shared `main`
everyone builds on. A short daily or twice-daily check-in call — "here's
what I decided and built since last time" — catches anything that slips
through the one-liners.

## Before starting a new session

A quick checklist before you open Claude Code to work on your block:

- [ ] Pull the latest `main` (or ask Claude Code to do it).
- [ ] Check the group chat for any "Decided: ..." messages since you last
      worked, so you're not building on a stale picture.
- [ ] Create a new branch for today's task, or switch to your existing one
      and make sure it's up to date with `main`.
- [ ] Know the one small task you're tackling this session — not "my
      whole block at once."
- [ ] If you want to see your change actually running against a real
      database (not just passing tests), confirm `.streamlit/secrets.toml`
      exists with real Supabase credentials. If the Supabase project
      hasn't been set up yet, that's Block D's job — check with them first.

## How to do this with Claude Code — no coding needed

If you can't read code, your job is reading Claude's plain-English answers
and checking the real app in the browser — never the code itself. Say
these things to Claude Code, in order, for whatever piece you're working
on (this example uses Identity & Lobbies, but swap the file names for your
own block from the table above):

1. **Setup, once:** "Pull the latest main, then create a new branch for me
   called `identity-lobbies-work`."
2. **Understand the design:** "I want to work on Identity & Lobbies. Read
   `docs/ontology` and tell me in plain English what's already decided for
   this area, and what's still an open question."
3. **Understand what's built:** "Now read the existing code for this —
   [the files for your block] — and explain in plain English what already
   works and what's missing."
4. **Say the rule you want, in plain English, no code:** e.g. "I want
   players to be able to leave a lobby they joined by mistake." If Claude
   says this touches something the team hasn't decided, stop and decide it
   together first, then say "update the ontology to say X" before
   continuing.
5. **Let it build and test:** "Please write this, including a test for it,
   run the full test suite, and tell me in plain English whether
   everything passes."
6. **See it actually work:** "Start the app and let me click through this
   in the browser so I can see it myself." A passing test is not the same
   as a working feature — check it on screen.
7. **Keep the docs honest:** "Now update `docs/ontology` to match what we
   just built, so the rest of the team has the same picture."
8. **Save and share it:** "Commit this with a clear message, push the
   branch, and open a pull request explaining what changed and why."
9. **Get it reviewed:** ask a teammate to look at the pull request before
   it's merged into main.

Repeat from step 4 for the next small piece of your block.

## Drink Entries presentation (Drink Entries & Scoring block)

Check-in and Lobby photos share `drink_entry_ui.py` and
`assets/drink_entries.css`. The helper renders escaped headings/context and
simple decorative SVGs; the stylesheet applies only when that page header is
present. Native Streamlit inputs keep their validation, labels and keyboard
controls. Change the colors/spacing there instead of changing game rules or
the shared account/navigation code. No new frontend dependency is needed.

Check the three-step check-in on a phone-width screen, category/size changes,
Shot without a size field, the points preview, the closed-window/cooldown
messages, correction and confirmed image deletion. Photo management remains
available after a failed image download; deletion keeps the score. The
automated workflows are in `tests/test_scoring_ui.py` and
`tests/test_photo_lifecycle.py`, including hostile display text and download
failure. Real camera/GPS and Supabase setup still need the integration checks
in `docs/SCORING_IMPLEMENTATION.md`.

The Standings page now shares the visual header and uses `standings_ui.py`
with `assets/standings.css` for the personal summary, ranked rows and territory
cards. It displays the existing core helper results, preserving their exact
quarter-points and tie order. It makes no new database writes. Keep future
Data-block changes in the existing core/repository helpers; use the UI module
for layout only. `tests/test_standings_ui.py` checks displayed totals, ties,
unranked/empty states, service failures and escaped public display text.

Authenticated pages now get the shared five-tab bottom bar from
`app_navigation.py`. For an existing session, `shared.require_login` handles
this generic bar before network reads; every destination verifies the account
before showing private data. Tabs: Map, Ranks (Leaderboard), the Check-in plus in the middle, Games
(Minigames), Profile. Lobbies and Photo history open from the Profile menu. Use native `st.switch_page` to keep login/session state; do not replace
these controls with hard browser links. Profile and Lobby retain their own
workflows. `assets/navigation.css` provides the fixed bar and content clearance.

Check-in mounts `camera_capture.py` / `components/drink_camera/` automatically,
then requires a photo before rendering drink/size choices. The browser still
controls camera permission. Capture stops the camera; Retake starts a new
capture. `phone_location.track_location()` starts at page entry, following the
phone's GPS automatically (no button); `current_location()` then validates the
newest reading with `core.location.parse_phone_reading`. R-L01–R-L04 accept at
most 50 m uncertainty and 60 s age and ignore photo GPS. No manual coordinate
inputs remain. The Map page (`pages/5_Map.py`, drawn by `map_ui.py`) uses the
same tracker plus `core.territories.capture_status` for "points needed to take it". Photo history lists up to four authorized images per page,
with cards rendered by `photo_history_ui.py`; View details retains correction
and deletion controls. Keep inline image bytes so private images never get a
public Streamlit media URL. Test the routes, photo gate, gallery paging,
entry selection and membership denial alongside the existing workflow tests.

Create lobby / Retry setup can explicitly select a QA season, with a frozen
Wednesday 08:00–Sunday 18:00 window. Normal seasons keep Thursday 18:00–Sunday
18:00. See `docs/CAMERA_AND_QA_SEASONS.md` for setup and verification.

## Profile friends (Identity block)

`pages/1_Profile.py` reaches `friends_ui.py` through `profile_ui.py` after login.
The Friends view has four native card buttons styled by `assets/friends.css`.
Each opens one dismissible dialog; Profile actions keep it open after saving,
with a success notice and fresh data. Removal uses an inline confirmation.
The optional success notice in `friendship_action` is used only by Profile;
Lobby controls keep their existing behavior. No migration is needed for this
layout change. `core/friends.py`
contains search and request rules and needs no database. `data/db.py`
fetches only public usernames for search, loads the current player's
relationships, validates an action, then calls `save_friendship` to save
it only if the relationship version has not changed. The SQL transaction
serializes updates for a player pair, including the first request.
Apply `migrations/006_friendships.sql` once to an existing database.
No Player fields or lobby behavior change. See RULES.md F1–F5.

Verify with `python -m pytest tests/test_friends.py tests/test_friends_ui.py tests/test_friends_db.py -q`. With a configured database,
use two accounts: search, request, accept, check both lists, remove,
request again, cancel, request again and decline. Try again immediately
(rejected), then at ten minutes (allowed). A third account must see
neither friendship nor requests. Restart Streamlit and log back into both
accounts to confirm saved requests/friends and decline timestamps survive.

## Lobby overview (Identity block, 18 November 2026)

`pages/2_Lobby.py` calls `lobby_ui.py` for the visible
joined-lobby list. `core/lobby_overview.py` derives status/countdown from saved
Season dates; `assets/lobbies.css` styles green running/grey past cards. Leaders
come from `season_leader`; pictures use the existing authorized byte loader.
No new shared model fields or runtime dependencies are needed.

The contributor replaced same-lobby season renewal with R-R03: one competition
per lobby. `data/db.py` rejects renewals early; migration 009 enforces the rule
atomically, including direct inserts. Existing history remains intact. Review
and apply 009 after 005 before deployment. Verify with `python -m pytest -q`
and `python scripts/verify_single_competition_lobbies.py` (optional local SQL
test tools as in LOBBY_MIGRATION_REVIEW.md). For deployed verification, join two
running lobbies and one finished lobby, check newest-first auto-selection,
private-picture initials, card navigation and View leaderboard; restart, log in
again, and confirm the same saved dates/results and ordering remain. A lobby
at its finish boundary must reject check-ins and appear as past on refresh.

### Lobby members and friend requests (18 November 2026)

`lobby_ui.py` adds invite codes to joined cards. A native button styled over
all of each card opens a native member dialog over the blurred overview.
The card shows View lobby →. CSS stretches both Streamlit's element wrapper
and the button over the card; stretching only the button leaves its click
area below the card. For browser QA, click the card's title, centre and
bottom action area and verify each opens the popup, then check keyboard focus.
In individual mode the popup contains the name, invite code, scrollable member list and a
View leaderboard button below it, with no top-three preview. All native
close paths clear the opened-lobby session state so refresh cannot reopen it.
`lobby_forms_ui.py` holds Create/Join dialogs. Opening one closes the member
popup; only one dialog is called in a run. Creation/join success opens the
member or team popup with a notice. An initial season-start failure keeps Retry
lobby setup available in that popup. Member controls reuse
`friends_ui.friendship_action` and the existing `core/friends.py` and database
transition logic, so Profile and Lobby read/write the same relationships.
No migration or new dependencies are needed (existing migration 006 is required).
Friendship lookup failures keep the username list but hide actions; membership
is checked again before loading usernames or friendship state.

Verify with `python -m pytest tests/test_lobby_ui.py tests/test_friends_ui.py
 tests/test_friends.py tests/test_friends_db.py -q` (one line). The AppTest
workflow sends requests, opens fresh sessions, accepts/declines, rejects a
request during the decline cooldown, and checks access/error states.
With a configured database, use two accounts in one lobby: send a request,
refresh as the recipient, decline then verify the cooldown; later send again
and accept. Restart Streamlit and confirm the request/friendship remains in
both Lobby and Profile. These live database/restart checks remain manual.

## Team lobbies (Identity, Scoring and Standings)

See [TEAM_MODE.md](TEAM_MODE.md) for the cross-block handoff, migration 010,
source mapping and verification commands. This contributor-authorized shared
model change adds teams without changing individual lobbies. Replay uses
saved entry team identities for totals, territory ownership and income.
Every teammate should explain why team joins/scoring use one database lock,
why a teammate does not pay owner income, and why a scored member cannot
switch teams. Rule source: R-TEAM01–R-TEAM05 in the ontology.

Team mode is integrated into these same entry points. `lobby_forms_ui.py`
contains the mode/count/capacity/assignment controls; the card router opens
`team_ui.py` for teams and the member/friend dialog for individual lobbies.
Both use `_opened_lobby_id` and clear it on dismissal; `_lobby_dialog` is
reserved for Create/Join. Opening Create/Join closes either detail popup,
and successful creation/join selects the saved lobby and opens its matching
popup. This preserves the member UI from main and the team competition rules.


## Remembered lobby context (18 November 2026)

`lobby_selection.py` owns session context and restoration. `shared.require_login`
restores after authentication, before any page uses the context. The Lobby
page saves explicit choices through `data/db.py`; closing a dialog keeps the
context. Migration 012 stores one preference per account behind service-role
access. Do not treat a saved lobby ID as authorization; existing membership
checks still run on every protected workflow. See the remembered-selection
workflow in `docs/ontology/WORKFLOWS.md` and the migration/verification steps
in README. Automated fresh-session tests mock the persistent data service;
migration 012 was applied on 18 November 2026, with seven SQL checks passing
and fresh-process persistence verified against the configured Supabase project.
Temporary verification records were removed. A deployed browser restart check
remains a release step.

## Page responsiveness and shared styling

See [PAGE_PERFORMANCE.md](PAGE_PERFORMANCE.md) for the 18 November cleanup,
query/replay changes, reproducible benchmarks and verification. Reuse each
page's fresh validated account/season context instead of loading it twice.
Map and Leaderboard share one score replay within their page render. Keep
authorization fresh on every full page run; do not add a global account cache.
Shared fonts, spacing, borders and shadows live in `assets/theme.css`.

## Focus Challenge handoff — 19 November 2026

The second Minigames card opens the saved three-stage Focus game in new seasons
whose frozen rules enable it. `core/focus_challenge.py` owns configuration and
message validation; `focus_challenge_ui.py` plus the component handle presentation.
Migration 015 also enables existing explicitly marked v1 QA seasons without
rewriting snapshots: zero uploads, unlimited sequential attempts after failure
or success, and play throughout the active season. Each win refreshes a single
x1.5 hour, never stacks it. Normal seasons retain their existing gates.
Migration 014 owns accepted-entry gates, persisted challenge/progress, deadlines
and exactly-once rewards. `DrinkEntry.focus_attempt_id` preserves each boosted
award through corrections and replay, and owner income now supports exact eighths.
See [FOCUS_CHALLENGE.md](FOCUS_CHALLENGE.md) for commands, Data activation and
security limits. Both building-block owners should review the shared data/scoring
change before merge. The contributor reported teammate agreement on the design.
