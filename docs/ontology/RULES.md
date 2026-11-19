# Rules

## Minigames

### R-M06 Focus Challenge unlocks and attempts

Players see this game as **Reaction Test** (renamed on screen 19 November
2026); the rules, code and saved data keep the name Focus Challenge.

Team approval reported by the contributor on 19 November 2026. New v1 seasons
whose frozen snapshot contains `focus_challenge.version = 1` enable this game.
Existing snapshots are not edited. The following gates apply to normal seasons.
Contributor-approved QA exception, 19 November 2026: the frozen JSON boolean
`scoring_rules.test_mode=true` enables Focus immediately, including existing v1
test seasons without a Focus snapshot. No uploads are required; failed and
successful attempts can be replayed sequentially without a nightly limit.
Names, string values and normal seasons never enable the exception. Migration
015 supplies the fixed v1 configuration for older QA snapshots without editing
them. QA games may run any time during an active season, including outside the
weekly scoring window; drink submissions still require their normal window.

Count the member's accepted v1 drink entries in this lobby/season and the same
06:00-based evening, irrespective of type/size. Their shared Chug Duel entry
counts once. Retakes, rejected submissions and duplicate retries do not count;
deleting an image preserves its accepted entry and this count under R7.
The first attempt unlocks at five entries, then at seven, nine, eleven, etc.
after failures. Starting atomically consumes that attempt; simultaneous starts
recover the same saved attempt. Focus and Chug Duel allowances are separate.
Only one game may be actively running for a member at a time.

### R-M07 Focus Challenge tasks and variation

Pass reaction, memory and precision consecutively. Contributor revision,
19 November 2026: new attempts use one signal and a tap within 220 ms; no early
taps. Migration 021 supersedes reaction-only migrations 018/019/020 and applies this
to new attempts in existing eligible seasons
without editing season snapshots. Attempt-level configuration preserves rules
for games already started before this revision. Memory requires reproducing seven
positions exactly. Precision requires twelve correct taps within twelve seconds;
a wrong tap ends the attempt. Difficulty is a pilot setting needing human phone
calibration, not a health benchmark. Passing is not a sobriety assessment.

Each new attempt receives private server-generated random material: independent
3500–6500 ms reaction waits, a fresh 3x3 memory sequence with no adjacent repeats,
and new valid precision positions. Refreshing cannot reroll it. Memory flashes
650 ms per position with 200 ms gaps, followed by fifteen seconds for input.
New attempts again require all three stages (contributor choice resolving PR #64).
Already-running reaction-only attempts retain their previous rules and
repeatable false starts.
For new three-stage attempts, an early reaction tap ends the attempt.
After passing reaction, press Start memory to begin its one-second lead-in
and preview. Passing memory opens Start precision. These ready screens keep
the next stage from starting unexpectedly during a page update.
Precision targets are 52 px with consistent normalized margins and minimum
movement; no colour-only matching is required.

### R-M08 Focus Challenge interruptions and deadlines

Resume the same persisted attempt and progress; its clock keeps running.
Ready screens have thirty seconds. New reaction signals allow 500 ms for a
response, but anything above 220 ms still fails R-M07. The whole attempt has a
three-minute maximum and ends sooner at 06:00, scoring closure (normal seasons)
or season end. A miss or timeout requires the next unlock count in normal
seasons; QA may retry immediately. Leaving the screen itself
does not create or refund an attempt.

The server allows two seconds for delivery of stage evidence, while browser
timers enforce the actual task budget. This does not extend the overall,
06:00, normal scoring or season cutoff. Timers use a monotonic browser clock anchored
to server timestamps. Replayed/stale messages recover the recorded result.
Precision checkpoints save full tap prefixes without blocking the next local tap.

### R-M09 Focus boost and scoring

In normal seasons one successful attempt per member/lobby evening grants x1.5 on
future ordinary drink season and matched-territory points for sixty minutes,
ending earlier at scoring closure or season end. It can continue past 06:00.
Boosts never exceed x1.5; an unexpired prior-evening boost blocks a new Focus
attempt until it ends. QA may replay while a boost is active; a further win
refreshes the hour rather than multiplying or adding the durations. QA boosts
end at the earlier of sixty minutes or season end, and never change when drink
submissions are accepted. Chug Duel entries/transfers keep their normal scoring.
The owner earns 25% of the boosted award as additional season income, using
the owner immediately before the entry as usual. No self/team-self income.

In team mode only the successful member's ordinary entries are boosted; their
awards add to the team totals. Teammates' other entries are unchanged. Eligibility
uses authoritative receipt time: boost start <= check-in receipt < expiry.
The entry stores its source Focus attempt. Corrections retain that original
multiplier and replay ownership/income without compounding or depending on
whether the boost is still active. Photo deletion does not remove awards.

Store awards as exact PostgreSQL numeric half-points. Existing
`owner_bonus_quarters` remains compatible but can contain half a quarter,
representing exact eighth-points: boosted 1 -> 1.5; owner income -> 0.375.
Display up to three decimals without rounding this income away. The server
determines rewards and awards; browser timing/tap evidence is trust-based and
does not establish automated anti-cheat or sobriety verification.

See [implementation and activation](../FOCUS_CHALLENGE.md).


### R-M10 Time Duel

Contributor-approved 19 November 2026: [Time Duel](TIME_DUEL.md) defines three
hidden-timer rounds on two phones, identical random 5–12 second targets,
independent outgoing/incoming nightly roles, abandonment and exact-tie rules,
and an automatic one-hour x1.25 **season-only** ordinary-check-in reward.
Focus retains its existing effects; only the higher active multiplier applies.
Shared migration 017 was applied on 19 November 2026. Teammate review and
deployment remain pending.


### R-M01 Chug Duel invitation and opponents

In a v1 season with scoring open, challenge another member of the same lobby.
The challenger selects a drink and size from the frozen scoring table; the
recipient must accept these terms on their own account/device. Both drinks
have that selection. Self-challenges and cross-lobby opponents are rejected.
In a team lobby both players need different teams. Recheck teams before start.
One pending outgoing invitation and one accepted/started duel per player are
allowed at a time. Decline/cancel before start awards no points.

Source: contributor's explicit answers, 18 November 2026. Operational defaults
are explained in [CHUG_DUEL.md](../CHUG_DUEL.md).

### R-M02 Two separate nightly allowances

Each member can play once as challenger and once as recipient per lobby and
game night. A night rolls over at 06:00 in the season timezone: 23:59 and the
following 00:01 share the allowance; exactly 06:00 starts the next one.
Other lobbies have independent allowances. Acceptance reserves both respective
roles atomically; starting consumes them. A rejected, declined, expired or
cancelled pre-start invitation consumes neither. A second acceptance cannot
reserve an already used role, including concurrent requests. The opposite
role remains available after a finished game.

Source: contributor's explicit answers, 18 November 2026. This is an explicit
exception to the earlier shared-one-minigame-per-night design for Chug Duel.

QA exception, contributor decision 18 November 2026: when the season's frozen
`scoring_rules.test_mode` is the JSON boolean `true`, players may challenge and
accept repeatedly without a daily/nightly count limit, including after a
started abort. Show Unlimited in both allowance indicators. A lobby name or
a caller-supplied flag cannot enable this. Existing QA seasons also qualify.
One pending outgoing invitation and one accepted/started duel per member still
apply, as do the scoring window, season end, photo/GPS rules, countdown,
two-minute check-in cooldown and exactly-once point transfer. A player may
repeat only after the previous game has ended. Normal seasons retain the two
separate nightly allowances. This is enforced in Python and migration 012.

### R-M03 Shared check-in and base-point transfer

After acceptance the host takes one shared fresh photo and supplies their
current accepted phone GPS for both players. Apply normal photo sanitation,
location, territory, season/window and per-member cooldown checks. Store two
linked normal drink entries in one transaction, each with its own private
copy of the shared image. Invalid evidence or either member's cooldown
rejects the entire start: neither gets a new entry or points. Exact GPS is
discarded after validation. Each image copy follows its owner's existing R7
deletion/retention policy. Duel drink/size selections cannot be corrected
individually after start; delete images without changing points as usual.

At start both get normal base season/territory awards and normal owner income.
At a recorded win transfer only the loser's drink's base season points to the
winner's saved member/team account. Two 3-point drinks yield 6/0 base season
points. Territory base points and all owner income stay unchanged. Result
retries award nothing extra. The transfer gets its own ordered scoring event
so earliest-reaching ties use result time. Within an exact same-event tie,
preserve the previously higher-ranked account. Replaying corrected unrelated
entries preserves the transfer and recalculates normal owner income.

Source: contributor's explicit answers, 18 November 2026. Supersedes the
items-only reward rule for Chug Duel. Earlier source entries are unchanged.

### R-M04 Shared-phone finish

The challenger hosts a split screen with one named half per participant.
Both press Ready, then the server starts a three-second countdown. Ignore
early taps; the first finish tap after GO wins. Only the authenticated host
can submit one of these two participants as winner. A nonparticipant,
recipient-device result, invalid winner or pre-countdown result is rejected.
First tap wins even when browser events arrive close together. Completed
results are immutable, including retries with a different winner. Physical
completion is trust-based; the app only records the tap.

Host presentation, contributor request 18 November 2026: once started, show
the two named halves in a fixed full-viewport board. Hide app navigation and
disable page scrolling through Ready, countdown, GO and the outcome. Keep
the same board mounted while the server arms the game; show all three
countdown seconds without restarting them on refresh polling. A compact
exit retains the existing no-winner abort action. Keep the confirmed outcome
visible until the host chooses Back to Minigames, then restore navigation.

Source: contributor's explicit shared-device decision, 18 November 2026;
three seconds and first-browser-event handling are operational defaults.

### R-M05 Expiry, interruption and navigation

Invitations expire at ten minutes (inclusive). Accepted setup and started
play each also have ten minutes, capped by the next 06:00 rollover, scoring
close and season end. An accepted pre-start cancellation/expiry releases
reservations. After start, either participant can end without a winner;
expiry does the same. Both retain their normal drink awards, no base-point
transfer happens and the used role allowances remain consumed. A connection
loss can resume the saved started game until expiry. A lost successful reply
recovers its existing start/result instead of creating another one.

Minigames is the Games tab, immediately right of the check-in plus in the bottom navigation.
Receiving accounts see incoming invitations and outcomes on that page through
automatic refresh. New games are blocked outside normal scoring availability.

Source: contributor's explicit interruption and navigation answers,
18 November 2026; accepted/start phase deadlines are operational defaults.

## QA season exception (18 November 2026)

For explicitly selected **test seasons only**, posting opens Wednesday at
08:00 inclusive and closes Sunday at 18:00 exclusive in the season's lobby
timezone. Create lobby / Retry lobby setup opt in with an unchecked checkbox;
the choice is stored as `scoring_rules.test_mode=true` with start weekday 2
and hour 8. Normal seasons retain Thursday 18:00–Sunday 18:00. All other rules
and server validation still apply, including GPS, photos, cooldown, points
and corrections. The snapshot stays frozen; existing seasons are not changed.
This exception does not change minigame night boundaries.
R-M02 additionally allows unlimited sequential minigame replays in these QA
seasons; it does not remove cooldowns or permit overlapping games.

This file will hold every decided game rule with an ID and its allowed, rejected and boundary cases.

## Scoring v1 working implementation

The contributor authorised implementation on 17 November 2026. The current
contract is [SCORING_V1.md](SCORING_V1.md); [the handoff](../SCORING_IMPLEMENTATION.md)
records the explicit boundary defaults and verification. It is implemented
on `Scoring`, awaiting teammate review and shared migration. Existing seasons
remain legacy; the new rules apply to new v1 seasons. The earlier
[planning proposal](SCORING_PROPOSAL.md) and three-page PDF are historical
review records, not a claim of current deployment.

## Ranking

### R-R01 Ties
When two Players have the same Points, the Player who reached that score first ranks higher.

Source: team decision, 2026-11-17.

## Season

### R-R02 Season length
A lobby's season length is chosen when the lobby is created, from exactly
three options: one week, one month, or three months.

Source: team decision, 2026-11-17.

### R-R03 One competition per lobby
A lobby runs for its chosen 7/30/91-day duration exactly once. At its
competition's end timestamp it becomes a past lobby automatically and cannot
start another season. Start a new lobby for another competition. Keep the
existing Season entity/IDs for scoring and history; retain older multi-season
records unchanged, using their latest competition for the overview.

Allowed: create/join a lobby and start its first competition, or retry setup
when no season was saved. Rejected: adding a second competition even after
expiry. Boundary: `now == ends_at` is past; existing check-in cutoff applies.
The database serializes season inserts per lobby to reject concurrent renewals.

Source: contributor decision, 2026-11-18; supersedes same-lobby renewal in the
earlier scoring contract. Photo access and ranking rules are unchanged.

## Territories

### R-T01 Territory set
The game has 48 Territories covering the whole north bank from Alfama and
Baixa to Carcavelos. Central Lisbon has 23 small or medium areas (8
hand-drawn ones in Bairro Alto, Santa Catarina, 3 in Santos and 11 filling
the centre). 24 large areas fill the rest of the way to Nova (Baixa,
Alfama, Graça, Avenida da Liberdade, Marquês de Pombal, Amoreiras, Campo de
Ourique, Lapa, Alcântara, Ajuda, Monsanto, Belém, Restelo, Algés,
Linda-a-Velha, Cruz Quebrada, Caxias, Paço de Arcos, Oeiras, Santo Amaro,
Carcavelos), with the Jamor golf course as its own area. In Carcavelos, the
Nova SBE campus (with the beach) has two small neighbours, Carcavelos
Centro and Rebelva. Neighbouring areas border each other; the outlines stop
at the coastline. Busy streets get small areas, quiet neighbourhoods big ones. Their outlines live in one shared file,
`data/territories.geojson`, as GeoJSON Polygons with a display `name`
(for example "Shortys") and a short, permanent `id` (for example
`shortys`: lowercase letters and digits, words joined by hyphens). The
file is drawn and edited in geojson.io. Every
lobby plays on the same Territories; each lobby's Seasons have their own
Owners.

The file is the only source of truth. The app reads it for the location
check and the standings, and copies it into the database's `territories`
table when the app starts, because saved drinks refer to a Territory by its
`id`. When the file changes (e.g. after a merge), the app notices on the next
page load and copies the new version; no restart is needed.

| Case | Outcome |
| --- | --- |
| Allowed | Adding, removing, renaming or reshaping a Territory by editing the file, as long as R-T02 still holds. A renamed or reshaped Territory keeps its `id`; only the `name` changes. A new Territory gets a new, unused `id`. |
| Rejected | A Territory without a `name`, with a missing or badly formed `id` (capitals, spaces, underscores), or with an outline that is not a closed Polygon; two Territories with the same `id` or `name`. The app refuses to load such a file. |
| Boundary | Changing an outline mid-Season does not move drinks that were already saved; their stored Territory stays. A Territory removed from the file stays in the database so older drinks still point at it, but it is no longer matched or shown in the standings. |

Source: Location & Territories block (Felix), 2026-11-17. Resolves D-03.

### R-T02 Territories never overlap
Neighbouring Territories may share a border but must never overlap, so a
location lies inside at most one Territory. Gaps between Territories are
allowed. A drink in a gap counts as outside every Territory (see R1).

| Case | Outcome |
| --- | --- |
| Allowed | Two Territories sharing an edge; empty space between Territories. |
| Rejected | Any area that lies inside two Territories. |
| Boundary | A location near or on a shared border belongs to the Territory that contains the measured point (R-L03). |

Source: Location & Territories block (Felix), 2026-11-17. Resolves D-03.

## Location

### R-L01 Location source
Right after login the app asks the phone for its location once per login
session, so the browser shows its "Allow location?" prompt straight away.
Whether the browser asks again on later visits is the browser's setting
(e.g. Safari: website settings → Location → Allow). The
Check-in and Map pages then keep following the GPS automatically; there is
no button. A
check-in uses the newest reading at the moment the player submits. GPS data
stored in the photo is not used. Readings stay in the open session only and
are never saved; only the check-in's result and territory are stored.

| Case | Outcome |
| --- | --- |
| Allowed | The newest automatic phone reading (R-L02, R-L04 apply). |
| Rejected | No phone reading (permission denied, no signal, unsupported browser) or a malformed one: Submit stays disabled, nothing is saved, and the page explains what to do (R2). Typed-in coordinates are not accepted. |
| Boundary | A photo with GPS data that points somewhere else does not change the result. With the app closed or the phone locked, tracking pauses; the next reading arrives when the page is open again. |

Source: Location & Territories block (Felix), 2026-11-17, updated 2026-11-18 (automatic tracking). Resolves D-09.

### R-L02 Accuracy limit
The phone reports how many metres its reading may be off. A reading off by
at most 50 m is accepted. A worse reading counts as uncertain: the
check-in is not saved and the player retries (R2).

| Case | Outcome |
| --- | --- |
| Allowed | Accuracy of 50 m or better. |
| Rejected | Accuracy worse than 50 m. |
| Boundary | Exactly 50 m is accepted. |

Source: Location & Territories block (Felix), 2026-11-17. Resolves D-10 (uncertainty).

### R-L03 Borders
An accepted reading belongs to the Territory that contains the measured
point, even if its accuracy circle reaches into a neighbouring Territory.
A point in a gap or outside every Territory counts as outside (R1).

| Case | Outcome |
| --- | --- |
| Allowed | A point inside a Territory, however close to its border. |
| Boundary | A point exactly on a shared border is assigned to one of the two Territories; which one is not defined. |

Source: Location & Territories block (Felix), 2026-11-17. Resolves D-10 (edge handling).

### R-L04 Fresh readings only
A reading may be at most 60 seconds old when it is used. The app refreshes
the reading at least every 30 seconds while the page is open, and whenever
the player moves more than 20 m.

| Case | Outcome |
| --- | --- |
| Allowed | A reading up to and including 60 s old. |
| Rejected | A reading older than 60 s: Submit stays disabled until a fresh one arrives. A reading time more than 60 s in the future (wrong phone clock or tampering) is invalid. |
| Boundary | Exactly 60 s old is accepted. |

Source: Location & Territories block (Felix), 2026-11-18. Resolves D-10 (age).

## Direction agreed on 17 November 2026

The user's updated direction replaces buddy confirmation. Exact values and
boundary behavior listed in `OPEN_DECISIONS.md` are not yet agreed.

| ID | Rule | Allowed / rejected / boundary outcomes |
| --- | --- | --- |
| R1 | A city is divided into territories. An accepted check-in with a matched territory contributes its points there. | Assign a territory only when location verification identifies one. A verified location outside every territory can earn season points only, subject to the same eligibility rules. |
| R2 | Check-in requires a drink type, a size, a fresh photo taken in the app, and automatic location verification. | If location is missing or uncertain, keep the photo and drink selection on the form so the player can retry. Save the entry and award points only after verification. Only the phone's GPS reading counts (R-L01, R-L02). Discard raw coordinates after verification. |
| R3 | New v1 seasons use the frozen category/size table in [SCORING_V1.md](SCORING_V1.md). | Four categories; sizes for beer/wine/mixed; one shot serving. Reject unsupported combinations. Large bonuses are already included. Legacy seasons keep their prior awards. |
| R4 | The player with the most points in a territory owns it. | A unique leader owns the territory. Ties follow R-R01. Initial ownership, scoring window and resets remain open. |
| R5 | In v1, the previous territory owner earns an additional 25% of another player's base award in season points only. | The visitor keeps full base points. No self-income, territory income or income cap. Use exact quarters, or eighth-points for Focus under R-M09; replay affected ownership/income after a timely correction. See [SCORING_V1.md](SCORING_V1.md). |
| R6 | Current lobby members see their own unexpired photos. Sharing with other players is OFF by default for all accounts and controlled by one account-wide switch in Profile → Account & security → Photo privacy. | The switch applies to past and future photos across all lobbies. In individual mode, another member needs the uploader's consent. In team mode, current members of the entry's saved team can view its photos internally regardless of the switch; opponents need the uploader and every current member of that team to opt in. Check membership and consent again before each image download, as well as filtering the gallery. See R-PH01 below. |
| R7 | The owner can delete their photo while keeping the drink entry and its awarded points. Photos expire 30 days after their season ends. | Only the entry's author may request deletion. Remove the stored image and mark its reference as deleted, preserving the score and standings. Deny photo access at the expiry boundary and remove expired files through scheduled cleanup. |

### R-PH01 Photo sharing and attribution

Contributor choices, 19 November 2026: a missing preference means OFF for
existing and new accounts. Only the signed-in owner can save their account's
preference. The current roster controls team consent even for old photos:
one new member with sharing OFF hides that team's photos from opponents.
An empty team grants no opponent access. Historical attribution uses the
team saved on the check-in, not a later team assignment; if an uploader has
left that team their own consent is still required for opponent access.
Lobby membership is required for every audience, including the owner.

Chug Duel's two image copies follow each entry owner's sharing setting
independently. One participant opting out does not block the other copy.
This can leave the same shared image visible through the other participant;
the control does not promise consent from every person pictured.

Solo photos have a stable player-coloured frame and username. Team photos
have a stable team-coloured frame, team name and uploader's username. Names
remain readable independently of colour. Deleted/unavailable photos keep
their attribution on otherwise visible history cards. Scoring, check-in
requirements, standings, corrections and R7 retention do not change.

Turning sharing OFF denies subsequent gallery/download requests; images
already delivered to a page, downloaded or screenshotted cannot be recalled.
No public image URL is generated. Missing consent denies sharing; a failed
consent lookup never falls back to serving the image.

## Implementation recommendations (not yet agreed rules)

- Capture the current device location when the player submits (R-L01).
- Validate location, configured drink/size, eligibility and score on the server.
  Determine territory from the location; do not trust a client-selected territory.
- Keep an accepted check-in's drink/size, base points, applied modifier,
  awarded points and rule version so its score can be explained later.
- Prevent retries or concurrent submissions from awarding points twice.
- Evaluate the modifier using ownership immediately before accepting the
  check-in; save points and recompute ownership atomically. This avoids a
  check-in changing the modifier used to score itself. Team agreement needed.

Location evidence can support a location check; it does not automatically
verify that the selected drink type/size is accurate or that it was consumed.

## Accounts (agreed 17 November 2026)

| ID | Rule | Allowed / rejected / boundary outcomes |
| --- | --- | --- |
| A1 | Game pages require authentication; first visit offers registration and login. | A returning player logs in without recreating an account. Logged-out access stops before any game content or actions. |
| A2 | Registration requires first name, surname, username, email and a personally chosen password entered twice. | Reject empty names, malformed email, mismatched passwords and passwords shorter than 8 characters. Eight characters are accepted; implementation also rejects whitespace-only passwords and bounds input length. |
| A3 | Username and email must each be unique, ignoring case and surrounding whitespace. | Duplicate submissions cannot create another account, including concurrent submissions. Only username is public; name and email stay private. |
| A4 | Login uses email and password, without registration email verification. Password recovery is available through the registered email (authorised 18 November 2026). | Incorrect credentials leave credentials and game points unchanged. The login screen offers Forgot password and a code-based reset form. |
| A5 | Existing game progress is preserved. | Keep player IDs and all linked game records. No account-upgrade screen is shown; legacy records without an email require administrator migration to use email login. |
| A6 | Profile offers one Create account / Log in selector. | Only the selected account form is shown. No upgrade controls; Log in offers Forgot password. |
| A7 | Login has an optional Remember password checkbox. | Checked: remember this device for 30 days using an opaque token, without storing the password. Unchecked: no persistent login. Logout revokes this device; password changes invalidate remembered access. Expired/invalid tokens do not authenticate. |

Login throttling (ten attempts per account per 15 minutes) is a security
implementation setting, not a scoring rule. Recovery requests and reset attempts
share this throttle. Brevo's HTTPS API sends recovery emails; SMTP is not required.

- A11 (authorised 18 November 2026): Forgot password sends a random 16-character
  hexadecimal code, grouped with hyphens for readability, to the registered email.
  The database stores only a hash bound to the current password hash. Codes expire
  at 15 minutes (the exact expiry is rejected) and can be consumed once, atomically
  with the password update. A new request replaces the prior code, with at least
  one minute between requests. Changing the password invalidates outstanding codes
  on their next credential lookup. Invalid input, missing/expired/used codes and
  throttled resets leave passwords and points unchanged. The new password follows
  A2 and must differ from the old one. Reset does not automatically sign in;
  existing active and remembered sign-ins fail their next credential check.
  Requests give the same public message for unknown accounts, throttling and email
  delivery failures. Delivery failures remove only their own pending code.
  Names, game records, player ID and email remain unchanged.

## Friends (agreed 17 November 2026)

| ID | Rule | Allowed / rejected / boundary outcomes |
| --- | --- | --- |
| F1 | Signed-in players search all app usernames, independent of lobbies. | Search is partial, ignores case and surrounding whitespace, and returns at most 20 results sorted by username. Empty search returns none. Search excludes yourself and exposes only username, never name, email or credentials. No profile pictures or new profile fields. |
| F2 | Friendship requires an explicit request and acceptance by the recipient. | Only the recipient may accept or decline a pending request; only the sender may cancel it. Reject self-requests, duplicate requests, requests between existing friends, and responses to non-pending requests. An opposite-direction request does not automatically accept. |
| F3 | Declining a request starts a 10-minute waiting period. | Neither player can create a new request for that pair before 10 minutes have elapsed; exactly 10 minutes is allowed. This pair-wide interpretation prevents reversing a request to bypass the wait. Cancellation does not start a waiting period. |
| F4 | Accepted friends appear in both players' private lists. | Each player can see only their own relationships. Either friend may remove the friendship, removing it from both lists. Removal allows a new request, which again needs acceptance. No friendship changes points, lobby membership or photo access. |
| F5 | Requests are managed on Profile or beside lobby members and stored across sessions. | Incoming requests offer Accept/Decline, outgoing requests offer Cancel, and accepted friends offer Remove. Refresh friends reloads changes made by other players; lobby member controls reload with Refresh lobbies and the 60-second lobby refresh. No email notifications. Concurrent actions cannot overwrite an unseen change. |

Implementation: `core/friends.py` holds validation and search rules;
`friends_ui.py` renders controls using the authenticated session's player ID;
`data/db.py` stores state through a version-checked database function. The
server service key is the only database role with friendship access.

### Profile edits (agreed 18 November 2026)

- A8: A signed-in player can change their own username, first name and surname.
  Registration name limits and case-insensitive username uniqueness still
  apply. Email is read-only. Player ID and all linked game progress/friends
  remain unchanged. An expired credential version cannot save an edit.
- A9: Password changes require the correct current password and a matching
  new password following A2. The new password must differ from the current
  one. Current-password attempts share the login throttle. Successful changes
  invalidate active and remembered sessions; the player logs in again.

### Profile pictures (agreed 18 November 2026)

- A10: A signed-in player may take a camera photo or upload a JPEG, PNG or
  WebP from their library in Edit profile. Show a circular centre-cropped
  preview; save only after Save picture. Saved pictures persist across visits
  and devices. The player can replace or remove their own picture. Without a
  saved picture, use username initials. Neither pictures nor changes affect
  points, memberships or account identity.
- A11: Show the picture left of the username in Profile, and beside that
  player in friend lists and incoming/outgoing requests. Only the owner,
  accepted friends and both participants of a pending request can retrieve
  it. Declining, cancelling or removing the relationship ends further access.
  Search results for unrelated players show initials. No lobby-wide avatar
  visibility is introduced. Previously downloaded copies cannot be recalled.
- A12: Profile pictures use private server-only storage. Accept at most
  10 MiB and 20 million pixels; reject unreadable/animated images. Preserve
  orientation, centre-crop to a 512-pixel square, flatten transparency to white
  and re-encode JPEG without embedded metadata. Current images remain until
  replaced or removed. Failed writes can leave inaccessible uploads; remove
  unlinked uploads after a 24-hour grace period through server maintenance.

### Lobby member controls (agreed 18 November 2026)

- Joined lobby cards display their invite code alongside the name, leader and
  timing. Only joined lobbies are shown.
- Clicking a lobby card opens a popup over the blurred/dimmed overview showing
  its name, invite code and, in individual mode, all current member usernames, including players
  with no points. This works for active, past, upcoming and incomplete lobbies.
  There is no top-three preview. View leaderboard below the members closes
  the popup and opens the full Leaderboard for that lobby. Close, ×, outside
  click and Escape dismiss it. Long lists scroll; no scoring rules change.
- Create lobby and Join with a code are separate top-of-overview buttons.
  Forms open in dismissible modals over a blurred/dimmed background. Cancel,
  ×, outside click and Escape do not save. Successful creation/join opens
  that lobby's member or team popup with a notice. Existing options and validation stay.
- Each member row shows only the viewer's relationship: You, Friends, Request
  sent, Incoming friend request with Accept/Decline, or Add friend. F2–F5
  still apply, including the decline waiting period and concurrent-write checks.
  No new friendship rules, account fields or lobby-wide picture access.
- Membership is rechecked before showing members. Service failures show an
  error; unavailable friendship state disables actions without hiding usernames.

## Team lobbies (R-TEAM01–R-TEAM05, authorised 18 November 2026)

### R-TEAM01 Competition mode and settings
The creator chooses Individual (default) or Team. Individual lobbies keep
existing rules. Team setup chooses 2–16 teams, 1–20 players per team, and
Random or Players choose. These are fixed settings, not editable after creation.
The capacity is a maximum, not a required roster: play starts immediately,
late arrivals are allowed until the lobby ends, and uneven rosters can occur.
Equal capacities do not guarantee equal participation. There is no normalization
of points by team size. Existing lobbies stay individual.

### R-TEAM02 Joining teams
Teams are created together with the lobby, initially named Team 1, Team 2,
etc. Players choose a team with space in manual mode. A player may switch
before their first accepted scoring entry; after that, assignment is locked.
A member without a team cannot score. Random mode assigns each arriving
member to a randomly selected smallest team with space; no manual switching
or reshuffling. Lobby capacity includes members who have not chosen a team.
Repeated lobby joins retain the same membership and assignment.

Rejected: full lobby/team, another lobby's team, changes after scoring,
manual changes in random mode, joining/switching at or after the finish.
Concurrent joins serialize on the lobby lock, so the final slot admits only
one member. Rejection changes neither membership nor score.

### R-TEAM03 Names and pictures
Only current members of a team can click its name to edit its name and picture.
Names are trimmed, 1–40 characters, without control characters, and unique
within the lobby ignoring case. Members may upload or take a picture, replace
it or remove it. JPEG/PNG/WebP, 10 MB and 20 megapixels maximum; existing
profile photo processing crops to 512×512 JPEG and strips metadata. Encoded
output is limited to 512 KiB. No picture uses initials as the avatar.
Names/pictures can be edited after play and do not change identity or points.
Team pictures are visible only within their lobby. Member profile pictures
retain A11 privacy; other members see initials when access is unavailable.

### R-TEAM04 Combined competition and territory ownership
Every accepted entry snapshots the member's team. The leaderboard ranks teams,
not individual contributions. A team's territory account sums all members'
base points in that territory; the highest total owns it. Ties keep the team
that reached the total first, using the existing database acceptance order.
Season totals combine the members' base awards and the team's owner income.

The existing 25% prior-owner income goes to the owning team when a rival
team scores there. A teammate's entry never generates owner income. The
visiting team keeps all base points. Income counts only toward the season,
never territory ownership. Outside entries earn team season points only.
Corrections replay combined ownership and downstream owner income from the
original event position. Photos/minigames remain attached to their submitting
player; cooldown and minigame limits remain per player, not per team.

### R-TEAM05 Persistence and authorization
Team settings, roster, names, sanitized pictures and entry team identities
are saved in PostgreSQL through migration 010. Assignment and scoring share
the same lobby lock; accepted entry identity is immutable. Team writes and
reads require the authenticated app's existing member checks; anonymous and
Supabase authenticated roles have no access to the team table or write RPCs.
Source: contributor's explicit team-mode choices, 18 November 2026.

## Profile statistics

Quiz Duel's contributor-approved point-stake exception, separate nightly roles,
team-purse rules and twenty-second rounds are defined in [QUIZ_DUEL.md](QUIZ_DUEL.md).
Individual quiz transfers adjust personal lifetime points; team quiz transfers
adjust team season scores and season wins without becoming personal drink points.

### R-P01 Lifetime statistics across active and finished lobbies

Profile → My stats shows four cards: Total points, Drinks, Lobbies played,
and Total Wins. Include all retained active and finished lobbies; do not
depend on the selected lobby. Include every season in multi-season lobbies.
Accepted scoring check-ins count immediately, including existing history.

Points sum the player's own accepted drink awards across those seasons, plus
personal territory-owner income in individual seasons. Replay each season
separately so corrections and owner income agree with standings. Team scores,
teammates' drinks and team owner income are excluded from personal points.
Drinks counts accepted positive-point check-ins, including verified outside
locations and entries whose photo has since expired or been deleted.
Lobbies played counts distinct lobbies with at least one such drink.
Total Wins counts completed seasons (`now >= ends_at`) won individually or
by the player's team, using existing leaderboard tie-breaking. An active
season's current leader is not a winner. A completed season counts even if
another season in that lobby is active. Empty seasons have no winner.

Allowed: five finished lobbies plus one active lobby with 11 personal points
each show 66 points and six lobbies played; leading the active season adds no win.
Rejected: counting a teammate's drink as one's own, a duplicate entry twice,
or an active season as a win. Boundary: a win counts at the season's end
instant; no history shows zero on all four cards. A history-load failure
shows an error rather than a partial total. No scores or entities are changed.

Source: contributor request and clarified answers, 18 November 2026;
active-lobby inclusion and completed-season-only wins confirmed 19 November 2026.

## Leaving and rejoining a lobby

### R-LB01 Departure preserves history

A signed-in member can choose Leave lobby inside the individual or team lobby
popup, review the consequences and confirm, or choose Stay in lobby. This works
before, during and after the competition. Departure sets `LobbyMembership.left_at`;
it does not delete the membership, entries, earned points, team assignment or
minigame history. The lobby disappears from the departing player's joined list.
Fresh membership checks deny further check-ins, corrections, games, team edits
and lobby photo viewing, including from an already-open page. Retained scores
remain in lobby/territory standings and personal lifetime statistics; existing
win and tie rules remain unchanged. Thus a departed player can still win.

### R-LB02 Owner income while absent

Previously earned personal territory-owner income is kept. Individual territory
ownership and territory points remain unchanged, but visitors' accepted drinks
pay no personal owner income to a member who is absent at their acceptance.
Rejoining resumes eligibility for future income; no missed income is backfilled.
Team ownership and income belong to the team and continue normally.

Each accepted entry records the absent membership IDs under the lobby lock.
Replay and corrections use this immutable roster snapshot, including when a
correction changes who owned a territory. This prevents a later departure or
return from changing previously earned income. Existing entries start with an
empty absent roster because departure was not available before migration 016.

### R-LB03 Return and interruptions

Joining again with the invite code restores the same membership, original
joining time, scores, team assignment, cooldown and minigame allowances. A team
slot remains reserved while absent and is shown as Left (slot reserved); leaving
does not let another player occupy it. Returning to a finished lobby restores
history access but does not restart its competition or reopen scoring.

Leaving is rejected while the member has an accepted/started Chug Duel or a
running Focus Challenge. Finish the game or wait for its existing timeout;
expired games are settled by the normal expiry rules when departure is retried.
Unaccepted duel invitations are cancelled on departure. A retry of an already
completed departure is harmless. The player's saved selection of that lobby is
cleared, and the UI can select another active lobby.

Allowed: leave after scoring, keep points in both statistics and standings,
return with the same identity. Rejected: leaving during an active game, acting
for another player, scoring while absent, editing an absence snapshot, claiming
a departed member's reserved team slot. Boundaries: scoring and departure share
the lobby lock; whichever is accepted first determines the absent roster.
Corrections never rewrite that roster. Saved departure and score history survive
a database restart.

Source: contributor request and explicit answers, 19 November 2026. Migration
016 was applied to shared Supabase with contributor authorization on
19 November 2026. All 19 schema/access/history checks and a fresh app-process
read/RPC check passed. Frontend review, merge, deployment and deployed browser
verification remain pending.

### R-LB04 Deleting a lobby

Only the player who created a lobby (its earliest membership, even if they have
since left) can delete it. Deleting hides the lobby for everyone: it leaves
every lobby list, nobody can open it, check in, or play minigames in it, and
saved lobby choices pointing at it are cleared. Nothing is erased: scores,
photos and history stay in the database, in the same spirit as R-LB01. Open
duel invitations and running duels are cancelled. There is no undo in the app.
Allowed: creator deletes after a second, deliberate click. Rejected: any other
player, even a current member, gets "Only the person who created this lobby can
delete it." Boundary: a retry of an already completed deletion is harmless.
Needs migration `017_delete_lobby.sql` (the app keeps working without it, but
Delete lobby fails until it is applied).

Source: contributor request, 19 November 2026 (who may delete and "hide, keep
history" are the implementer's decisions; the team should confirm).
