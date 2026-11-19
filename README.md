# WeGoPub

WeGoPub: a social drinking-game app where players log drinks with a photo
and GPS location, capture territories on a map, and compete on a season
leaderboard. Game design lives in [`docs/ontology/`](docs/ontology/) and
[`AGENTS.md`](AGENTS.md).

Quiz Duel (100 English questions, generated multiplication/logic, reserved
3–10 point stakes): [implementation and setup](docs/QUIZ_DUEL.md).
Migration 016 was applied to the shared project on 19 November 2026; no question
import is needed. New databases still apply 016 after 014. See the
[activation verification](docs/QUIZ_DUEL.md).

Time Duel (three hidden-timer rounds on two phones, one-hour ×1.25 season bonus):
[implementation, local verification and migration 017](docs/TIME_DUEL.md).

**Deployed URL:** https://wegopubnow.streamlit.app/

**Team:**
- Niklas Peter — 78399
- Felix Mellino — TODO (student number)
- Ben Schittkowski — TODO (student number)
- Nils Cuypers — TODO (student number)

Names above are inferred from git history and may be wrong — each member
should confirm their own name and fill in their student number before
submission.

## Hosting (deployed app)

The public app runs on **Streamlit Community Cloud** at
https://wegopubnow.streamlit.app/ and uses the team's shared Supabase project
(region West EU) as its database and photo storage.

- **Source:** repository `felixmellino/drinkingprojectprogramming`, branch
  `main`, main file `app.py`. Every merge into `main` redeploys the app
  automatically within a few minutes.
- **Python:** 3.14 (chosen when the app was created; it can only be changed by
  deleting and re-creating the app). Dependencies come from the pinned
  `requirements.txt`.
- **Secrets:** set in the app's Settings → Secrets, never in the repository:
  ```
  SUPABASE_URL = "https://<project>.supabase.co"
  SUPABASE_KEY = "<legacy service_role key, starts with eyJ>"
  ```
  Use the legacy `service_role` key (Supabase → Project Settings → API Keys →
  Legacy API keys). The newer `sb_secret_…` key is rejected with
  "Invalid API key".
- **Territories:** on its first start after a deploy, the app copies
  `data/territories.geojson` into the database (`shared.get_territories()`),
  so editing the file and merging is all that's needed.
- **Location on phones:** browsers only share GPS over HTTPS and after the
  player allows it. The app asks once right after login. On iPhone, if it
  says location is blocked: Settings → Privacy & Security → Location Services
  → Safari Websites → While Using the App; then in Safari tap "aA" →
  Website Settings → Location → Allow.
- **Before a demo:** the free plan puts the app to sleep after a few days
  without visitors. Open the URL once beforehand and click "Wake up" if shown.
- **Check-ins** are only scored Thursday 18:00 – Sunday 18:00 (lobby time);
  the map and location work at any time.

## Local setup

Requires Python 3.11+.

SDK upgrade and live photo-storage verification, including daily GitHub
Actions cleanup setup: [storage verification](docs/STORAGE_SDK_VERIFICATION.md).

The team uses one shared Supabase project. Ask the Data owner for its
credentials through a secure transfer and put them in the ignored local
secrets file. If that project already has the schema, do not run `schema.sql`
again. The Data owner applies reviewed migrations once for the whole team.
Each teammate then pulls the merged code and uses the same project locally.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill
in a real Supabase project's URL and key (never commit the real file — it's
gitignored). Use the **server-only service-role key** for `SUPABASE_KEY`; never expose it
in browser code. The account tables deny access through public/anonymous keys.

The app pins `supabase==2.34.1` to support the current Storage bucket
response, including its `versioning_status` field. Use Python 3.11 or newer
(Python 3.12 is also supported). After pulling this upgrade, reinstall
`requirements.txt` in your local environment and restart the app. Update
the deployed environment too. Keep using the team's server-only credentials;
an SDK upgrade does not require recreating the database or changing keys.

For a **new database**, apply `schema.sql` via the Supabase SQL editor.
Territories load automatically from `data/territories.geojson` into the
database the first time the app runs (see `shared.get_territories()`) —
no separate seed step needed.

For an **existing database**, back it up and apply only
`migrations/001_personal_accounts.sql` once, then
`migrations/002_remembered_devices.sql` once, then
`migrations/003_text_territory_ids.sql` once, then
`migrations/004_server_game_tables.sql`. Skip the ones already applied.
Do not recreate the tables.
The migration adds email, unique indexes, recovery codes and login throttling;
it keeps every player ID, membership, drink entry and score. It aborts safely
if existing usernames collide after trimming and ignoring capitalization.
Resolve such collisions with the account owners before retrying.
Migration 004 restricts game tables, including lobby invite codes, to the
server's service-role key. Fresh databases get these restrictions in the
schema. All app database access continues through `data/db.py`.

Password recovery uses Brevo's HTTPS API and the existing server-only
`issue_password_reset` / `consume_password_reset` functions from migration 001.
No new database migration is required if 001 is already applied. Configure these
server-only settings locally and in Streamlit Community Cloud → Settings → Secrets:

```toml
BREVO_API_KEY = "your-restricted-transactional-email-key"
BREVO_SENDER_EMAIL = "wegopub@outlook.com"
BREVO_SENDER_NAME = "WeGoPub"
```

Use a verified sender and a key with Transactional email access. Keep real keys
out of Git. With an Outlook sender, Brevo substitutes an `@brevosend.com` domain.
The team's configured key expires 18 February 2027 (and may expire after 90 days
of inactivity); replace it in Secrets before expiry. No Brevo dashboard template
is required: `password_email.py` sends HTML and plain text versions directly.

On Log in, choose **Forgot password?**, request a code and enter it with a new
password. Codes expire after 15 minutes, work once, and a new request replaces
the previous code. Requests have a one-minute per-account cooldown; requests and
reset attempts share the existing ten-attempt / 15-minute account throttle.
If no email arrives, check spam, Brevo's transactional Logs, sender verification,
API-key permissions/expiry and the daily sending quota. The public response stays
the same for unknown addresses, throttled requests and delivery failures.

Before merging, test a real reset in a test account on the branch with Brevo
configured: restart the app between requesting and consuming the code; verify
old-password rejection, new-password login, code reuse rejection and invalidation
of existing/remembered sign-ins. Also check a code at its 15-minute expiry. These
live checks must not reset a teammate's account.

To enable check-in photos, run
[`migrations/setup_checkin_photo_storage.sql`](migrations/setup_checkin_photo_storage.sql)
in the Supabase SQL editor after the `drink_entries` table exists. It adds the
capture-time column and creates the private `check-in-photos` bucket. It can
also run on a project that already has the column and a private bucket.
It removes exact GPS coordinates from legacy entries, keeping their points
and assigned territory. Re-run it if an older photo setup was already applied.

The script restricts direct access to membership, season, and drink entry
records to the server, and blocks anonymous and authenticated Supabase clients
from the photo bucket. The app checks the signed-in player's lobby membership
before serving an image. Player accounts keep the access restrictions from
the account migrations.

In the test project, save a check-in and reopen it under **Lobby photos**
after restarting the app. Verify access with a lobby member and an account
outside the lobby.

The [security and data handling protocol](docs/SECURITY.md) describes photo
access, upload limits, secrets, and the privacy decisions to complete before
collecting real player photos.

Owners can delete their photo in **Lobby photos** while keeping the score.
Before deploying photo privacy, apply
[`migrations/013_checkin_photo_privacy.sql`](migrations/013_checkin_photo_privacy.sql)
to both new and existing databases. Applied to the shared project on
19 November 2026; eight database checks and a fresh app-server read passed.
It adds a server-only account preference;
missing preferences mean OFF for everyone. Under **Profile → Account &
security → Photo privacy**, players can share past and future check-in
photos across all lobbies. Own photos remain visible; current teammates
retain internal team access. Opponents need consent from the uploader and
every current member of the photo's saved team. A new teammate with sharing
OFF hides existing team photos from opponents. Chug Duel copies follow
each owner's preference independently. Turning sharing OFF cannot recall
already viewed or saved images. Photo frames identify the player, or the
team and player in team mode. This changes gallery/image access, not scores.

Photo access ends 30 days after its season ends. The Data owner must schedule
`python -m data.cleanup_checkin_photos --apply` on the server at least daily
and monitor failures. Without `--apply`, the command only reports counts.
It removes expired photos and abandoned uploads older than 24 hours, keeping
all scored entries. Physical deletion happens on a successful cleanup run.

### Scoring v1 setup

After the base schema, account/territory migrations, server game-table security
and photo setup, apply [`migrations/005_scoring_v1.sql`](migrations/005_scoring_v1.sql).
Do not rerun `schema.sql` on the shared existing project. New projects also need
migration 005 after the base schema and photo setup.

Existing populated seasons remain legacy, preserving their points and rules.
New lobbies start scoring v1 with a chosen timezone. Each lobby runs one
competition; after its duration ends it stays in Past Lobbies and cannot be
renewed. Create another lobby for a new competition. Rules, timezone and
dates are frozen; historical points and ownership are preserved.

The new scoring provides the 1-5 category/size table, additional 25% owner
season income, exact quarters, Thu 18:00-Sun 18:00 lobby-time eligibility,
a shared two-minute cooldown and author corrections with downstream replay.
History includes point breakdowns and revision records. See the
[implementation/Data handoff](docs/SCORING_IMPLEMENTATION.md) and
[current ontology contract](docs/ontology/SCORING_V1.md) for defaults, testing
commands and the remaining live checks. The three-page PDF is the historical
team-review proposal. Camera and phone GPS now start automatically when
Check-in opens. For Wednesday testing, create a new lobby with **Test season**
selected; its window is Wednesday 08:00–Sunday 18:00. Normal and existing
seasons retain their rules. See [camera and QA seasons](docs/CAMERA_AND_QA_SEASONS.md).

### Run the app

```bash
streamlit run app.py
```

### Run the tests

```bash
pytest
```

The test suite covers pure logic and Streamlit forms with mocked database
services; it needs no live Supabase connection. Run from the repository
root. The mocks do not verify PostgreSQL migrations.

## Accounts

Profile has one Create account / Log in selector; only the chosen form is shown.
Password recovery and account upgrades are currently unavailable.
First visit shows registration and login. Every game page requires a signed-in
account. Registration requires first name, surname, unique username, unique
email and a password of at least 8 characters, entered twice. Email and
username uniqueness ignore surrounding whitespace and capitalization.
Email verification is not required. Only the username is public.

Returning players log in with email and password. The optional **Remember
password** checkbox keeps the device signed in for 30 days. It saves a random
opaque token in browser local storage and only its hash in Supabase; no password
is saved in the browser. Remembered access survives a browser or app restart.
Unchecked means login lasts for the current Streamlit session only. Logout
revokes the current device's token and clears its storage; a password change
invalidates all remembered tokens. If browser storage is blocked, login still
works for the current visit. Serve the deployed app over HTTPS.

On reconnect, each new server session requests the saved token with a fresh
request ID, even if the browser's storage component is still open. The account
form waits for that read before appearing. Regression coverage in
`tests/test_account_ui.py` checks delayed reads and lost server state; token
expiry, password changes and logout remain covered by
`tests/test_remembered_sessions.py`.

Existing player IDs and all linked game records are retained. Legacy accounts
without an email cannot use email login: an administrator must link the correct
email and replace their credential hash while retaining the original player ID.
There is no self-service PIN upgrade flow.

Logins allow ten attempts per account per 15-minute window.
Password changes invalidate previous sessions on their next action.
Logout clears the browser session and remembered device; accounts and progress remain in Supabase.

### Verify against a configured Supabase project

1. Apply the migration to a copy of existing data; confirm player IDs,
   membership IDs and drink entries remain unchanged.
2. Log in with a test account and confirm the same lobby and standings after
   restarting Streamlit. The player
   may need to select their active lobby again after logging in.
3. Try a duplicate username/email with different capitalization and invalid
   or mismatched passwords. Confirm no account or points are added.
4. Tick Remember password, close and reopen the app, and confirm login is
   restored without entering credentials. Log out and reopen: login must be
   required. Repeat with the checkbox unticked; a fresh browser session must
   require login. Verify an administrator password change also cancels remembered access.
5. Open each game page while logged out. Confirm no game content is shown.
   Verify an anonymous Supabase key cannot read players/remembered-device records or
   call the account RPCs.

This live migration/restart check still needs the configured Supabase
project; the automated suite does not replace it.

## Project structure

- `core/` — every game rule, as plain Python with no Streamlit/database
  imports. This is what the tests cover.
- `data/db.py` — the only file that talks to Supabase.
- `account_ui.py` — one account form with registration and login.
- `device_login.py` and `components/remember_device/` — persistent device login.
- `phone_location.py` and `components/phone_location/` — automatic phone GPS for Check-in and Map.
- `map_ui.py` and `pages/5_Map.py` — territory map coloured by owner.
- `migrations/` — changes for already-populated databases.
- `pages/` — one Streamlit screen per file; each only calls into
  `core`/`data`, no rules live here.
- `tests/` — one file per `core/` module.

New here, or working on a building block? Read
[`docs/WORKING_GUIDE.md`](docs/WORKING_GUIDE.md) first — it explains every
file in plain language, how `docs/ontology/` connects to the code, the
four building blocks, and the team's workflow rules.

## Known gaps in this first increment

- **Testing GPS on a laptop:** Check-in and Map only use the browser's real
  location, followed automatically. To test or demo a territory you're not
  standing in, open Chrome DevTools → More tools → Sensors → Location and set
  the coordinates (e.g. 38.7133, -9.1456 lands in Shortys).
- **Chug Duel is implemented and merged.** Migration 011 was applied to the
  shared database on 18 November 2026; live setup checks passed. New databases
  need 011 after 010, then 012 for unlimited QA-lobby minigame replays.
  Migration 012 was also applied to the shared project on 18 November 2026;
  the QA replay UI update requires deployment with the new Python code.
  Normal lobbies keep their nightly limits. Real two-phone gameplay remains to verify; see
  [CHUG_DUEL.md](docs/CHUG_DUEL.md).
  Focus Challenge is implemented; migrations 014 and 015 activate existing explicit test seasons and new normal seasons. Quiz Duel and Time Duel are implemented with activation notes linked above. See the build order in
  `AGENTS.md`/the project plan for what's next.
- Scoring v1 has an implemented point table and weekly window. Legacy/minigame
  constants and calendar-month season
  semantics still need team review; see `docs/ontology/OPEN_DECISIONS.md`.

### Profile friends

For existing databases, apply `migrations/006_friendships.sql` once after
migration 004. Fresh databases running `schema.sql` already include it.
Restart the app, log in and open **Profile**. Search any player's username
(partial and case-insensitive), send a request, then use the recipient's
Profile to accept or decline. Outgoing requests can be cancelled; either
friend can remove the friendship. Friends lists are private, and a decline
prevents either player from sending another request for that pair for ten
minutes. Use **Refresh friends** to load actions made by another player.

Tests: `python -m pytest tests/test_friends.py tests/test_friends_ui.py tests/test_friends_db.py -q`.
The UI tests use a persistent fake repository across fresh Streamlit
sessions. Real PostgreSQL concurrency, migration installation and saved
state after a server restart still require verification against Supabase;
see the Profile friends checklist in `docs/WORKING_GUIDE.md`.

Migration `005_scoring_v1.sql` adds scoring; `006_friendships.sql` adds
friends. The friendship migration was previously named `005_friendships.sql`;
only its filename changed. If the old filename was already applied, do not
run it again under the new name. Existing databases need each feature's
migration once. Fresh databases already include friends in `schema.sql`, but
still need `005_scoring_v1.sql` after photo setup as described above.

### Profile menu

Profile opens Edit profile, Friends, My stats and Account & security as
separate views with Back to Profile. Log out signs out immediately. Players
can edit username/first name/surname; email stays read-only. Password changes
require the current password and sign out all devices. Account & security keeps
private name and email above Photo privacy and Change password buttons. Each
opens a dismissible popup; closing discards unsaved inputs, and privacy saves
show confirmation inside the popup. My stats shows Total points, Drinks, Lobbies played and Total Wins across
active and finished lobbies, independently of the selected lobby. Accepted
scoring check-ins count immediately, including existing history.
Points include the player's own drinks and individual
territory-owner income; team scores and team owner income are excluded.
Total Wins includes both individual and team victories in completed seasons
only; currently leading an active season does not count as a win.
Name/password changes need no new migration beyond the account indexes/access
rules already described above. Profile pictures need migration 008 below.

Validation: `python -m pytest tests/test_profile.py tests/test_profile_ui.py tests/test_account_ui.py tests/test_friends_ui.py -q`.
Before deployment, use a test account to save a name change, restart Streamlit,
then verify it remains saved and its friends/scores remain linked. Change that
test account's password, verify old credentials and remembered devices fail,
and log in with the new password. Automated persistence checks use a fake
repository; they do not replace this live Supabase check.

### Profile pictures

The Data owner applies [`migrations/008_profile_pictures.sql`](migrations/008_profile_pictures.sql)
after account setup, for both new and existing databases. It creates the
server-only picture reference table and private `profile-pictures` storage
bucket. Do not rerun `schema.sql` on the shared project. Friends visibility
also needs the existing `006_friendships.sql` migration.

Edit profile offers Upload photo / Take photo, an automatic circular centre
crop preview and Save picture. JPEG, PNG and WebP are supported (10 MiB,
20 megapixels; still images). Saved pictures persist across devices. Replace
or Remove picture is available; removal shows initials. Pictures appear in
Profile and friend lists/requests, with access checked against current
accepted/pending relationships. They do not appear in unrelated search results.

Schedule `python -m data.cleanup_profile_pictures --apply` daily to remove
unlinked uploads older than 24 hours; omit `--apply` for a dry run. Current
pictures are kept. Apply the migration and complete the live camera/library,
restart and audience checks in `docs/SECURITY.md` before claiming deployment
verification. These scripts have not been applied to the shared project by
this local implementation.

Tests: `python -m pytest tests/test_profile_photo.py tests/test_profile_picture_db.py tests/test_profile_picture_ui.py -q`.

### Lobby migration 007 compatibility revision

After schema/account setup and `005_scoring_v1.sql`, the revised
[`007_lobby_battles.sql`](migrations/007_lobby_battles.sql) adds a private,
read-only lobby snapshot view. It preserves the current create/join/start
flow and scoring rules. Use the revised file from reviewed, merged `main`;
the original recovered SQL in PR #17 is incompatible and must not be run.
If an old `lobby_states` table already exists, stop for separate migration
review. Do not drop it or rerun the base schema. No new runtime dependencies
or application write calls are required. Friends and profile-picture setup
are independent.

The owner-managed lobby feature remains deferred. See
[`docs/LOBBY_MIGRATION_REVIEW.md`](docs/LOBBY_MIGRATION_REVIEW.md) for the
scope, deployment checks and exact disposable PostgreSQL test commands.

### Lobby cards and fixed duration (18 November 2026)

Lobby lists all joined lobbies directly: running competitions newest-started
first in green, then Past Lobbies newest-finished first in grey. It selects
the newest running lobby automatically. Clicking anywhere on a card opens
a popup showing the lobby name, invite code and all members over the blurred
lobby overview. Long member lists scroll. View leaderboard below the list
closes the popup and opens the full Leaderboard for that lobby; there is no
top-three preview. Close, ×, outside click and Escape dismiss the popup.
Member rows offer Add friend or Accept/Decline for incoming requests, with
You/Friends/Request sent status where appropriate. Create lobby and Join with
a code are separate buttons above the list, opening dismissible dialogs over
a blurred/dimmed background. Successful creation/join opens the lobby member popup.
Cards use public usernames, existing
ranking/tie rules, and authorized profile pictures with initials as fallback.
No scores shows **No Leader**, including finished lobbies. Create and join
remain above the list. The countdown/list refresh every minute while open.

Apply [`migrations/009_single_competition_lobbies.sql`](migrations/009_single_competition_lobbies.sql)
after migration 005 for atomic database enforcement of one competition per
lobby. Existing multi-season history is retained; its latest competition
summarizes that lobby. No season renewal control remains. A failed initial
season setup can be retried in the incomplete lobby’s member popup.

Validation: `python -m pytest -q`; optional disposable SQL checks:
`python scripts/verify_single_competition_lobbies.py` with the isolated test
packages documented in `docs/LOBBY_MIGRATION_REVIEW.md`.
Shared database installation and deployed/restart checks remain the Data
owner's integration step after review; no migration runs on app startup.

## Individual and team lobbies

Create lobby offers Individual (default) or Team, with team count, maximum
members per team and random/manual joining. Team members can rename their
team and take/upload a team picture. Combined team points decide both the
leaderboard and territory ownership. Existing lobbies remain individual.
Before using team mode, the Data owner must review/apply
[`migrations/010_team_lobbies.sql`](migrations/010_team_lobbies.sql) after 005
and 009. See [setup, code handoff and verification](docs/TEAM_MODE.md).


### Remembered lobby selection

Apply [`migrations/012_player_lobby_choices.sql`](migrations/012_player_lobby_choices.sql)
once before deploying this version (also required for new databases).
It adds a server-only account preference; existing Player/Lobby models and
scoring records are unchanged. The last explicitly selected lobby follows the
player across devices. Reopening switches a finished selection to the newest
active lobby. Removed membership requires selecting a lobby again.

Verify locally with `python -m pytest tests/test_lobby_selection.py tests/test_lobby_ui.py -q`.
These tests exercise fresh Streamlit sessions, real Leaderboard initialization,
account isolation, expiry fallback, access rejection and save failures with a
mock data service. Migration 012 was applied to the configured Supabase project on 18 November
2026: all seven SQL checks passed, and a saved preference survived a fresh
Python process/database client. Nonmember writes were rejected without
changing the preference; all temporary test records were removed.

Browser verification on 18 November 2026 passed in a freshly started local
app against the shared database: choose the older of two active QA lobbies,
close its popup, open Leaderboard, fully reload the page and sign in again
without opening Lobby. Leaderboard restored the older chosen lobby correctly.
The temporary QA account and both lobbies were removed after verification.

The public app still showed the old lobby-selection prompt on direct
Leaderboard access during the same check. Deploy this branch's app changes,
then repeat the browser check at the public URL. Finished-lobby fallback and
revoked membership are covered by automated tests; deployed browser checks
remain. The automated suite uses mocks and does not apply migrations or
require database credentials.

### Focus Challenge (19 November 2026)

The second playable minigame adds randomized reaction, seven-step memory and
precision tests. The selected flow uses one reaction within 220 ms, Start memory,
then Start precision. Apply [`migrations/021_focus_three_stage_flow.sql`](migrations/021_focus_three_stage_flow.sql)
last, after 015 and any already-installed 018/019/020 changes; it includes the optional
017 Focus setup and preserves running games. Migration 021 was installed on the
shared project on 19 November 2026. Start a new attempt after refreshing the app;
already-running reaction-only attempts keep their previous rules.
Accepted entries unlock attempts at five, then seven/nine/etc.
after failures. One win per evening grants a personal 60-minute x1.5 ordinary
season/territory effect, including 25% owner income on boosted awards.
Chug Duel scoring is unchanged. Before activation, the Data owner applies
`migrations/014_focus_challenge.sql` after 011, `012_qa_minigames.sql` and
`013_checkin_photo_privacy.sql`, then applies `015_focus_test_replays.sql`.
Existing explicitly marked test seasons can play immediately without uploads,
including unlimited sequential retries/wins throughout the active season.
Repeated wins refresh the single x1.5 hour. Normal seasons retain 5/7/9 unlocks,
one win per evening and their scoring window; older normal snapshots stay frozen.
See [the setup, security limits and verification record](docs/FOCUS_CHALLENGE.md).
Shared Focus migrations 014/015/021 are installed. The database verification
confirmed one reaction, a 220 ms limit and three-stage flow; status RPC checks
confirmed zero-upload, unlimited play in all nine populated test seasons.
Real-phone difficulty calibration and complete deployed gameplay still need verification.

### Minigame invite badge

Apply [migration 022](migrations/022_quiz_duel_invite_list.sql) so Quiz Duel lists
all pending invites. Apply [migration 023](migrations/023_minigame_invite_badge.sql) and
[migration 024](migrations/024_minigame_tile_badges.sql) after the Chug,
Quiz and Time Duel migrations. The Games tab checks every 10 seconds for pending
incoming invitations in the selected season. The catalogue checks every 3 seconds
and shows the count on each duel's tile. Open the game to respond or manage
a challenge you sent.

### Leaving and rejoining lobbies

Open a lobby and choose **Leave lobby → Confirm leave**. Scores remain in lobby
standings and Profile → My stats, including earned owner income. Personal owner
income pauses while absent. Rejoin using the original invite code to restore
the same membership, history, team and game limits. Team slots stay reserved;
accepted/running duels and running Focus attempts block leaving until finished
or expired. Team owner income continues normally. See R-LB01–R-LB03.

Delete lobby (creator only, hides the lobby, keeps history; R-LB04) needs
[`migrations/017_delete_lobby.sql`](migrations/017_delete_lobby.sql) **after 016**.
It is **not applied** to Supabase yet. It passed a local in-memory Postgres
check (creator/other/retry, history kept); apply it before deploying this code.

Before using this feature, the Data owner applies
[`migrations/016_leave_lobby.sql`](migrations/016_leave_lobby.sql) **after 015**
and `012_player_lobby_choices.sql`. Apply the migration before deploying this
code. It runs no migrations automatically and does not delete existing history.
Migration 016 was applied to the shared Supabase project with contributor
authorization on 19 November 2026. All 19 schema/access/history checks and a
fresh app-process read/RPC check passed. The frontend changes still need
review, merge and deployment before the public app shows the button.

Verification:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_leave_lobby.py
```

The second command uses disposable local PostgreSQL with the optional
`pgserver==0.1.4`, `psycopg[binary]==3.2.13` and `fasteners==0.20` tools described
above. It verifies access denial, scoring/replay parity, game interruption,
reserved team slots and persistence after a database restart, using synthetic
data and no Supabase connection.
