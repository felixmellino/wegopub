# Workflows

## Focus Challenge in test seasons

In an explicitly marked v1 test season, open Minigames → Focus Challenge →
Start. No uploads or new season are required, including for pre-Focus QA
snapshots once migrations 014 and 015 are installed. The UI labels test mode
and hides the upload-unlock progress. Finish/resume the saved attempt before
starting another. After a failure or win, return to games and start again.
Repeated wins refresh the single x1.5 hour; they never stack multipliers.
Test games work throughout the active season; expired seasons remain closed.
Check-in scoring still uses its own weekly window. Normal-season gates,
deadlines, membership checks and Focus/Chug running-game exclusion still apply.
The current server response determines test-mode availability, including when
a page holds an older season snapshot. QA has no upload-progress division;
an invalid normal unlock threshold shows a reload message and prevents start.

> Scoring v1 implementation was authorised on 17 November 2026. See
> [the current contract](SCORING_V1.md) and [Data handoff](../SCORING_IMPLEMENTATION.md).
> Earlier scoring drafts below are historical where they differ. Legacy seasons
> retain their old behaviour; migration and teammate review are pending.


## Check in and score

Updated direction: automatic location verification replaces buddy confirmation.

1. Player taps the central +. Check-in opens a full-viewport camera stage
   with bottom-centre shutter, front/back switch and Close, while starting
   live phone-location tracking. Browser camera/location permission
   remains necessary; a previously granted permission avoids an extra app step.
2. Player takes a fresh photo with the shutter. The camera stops and the
   app automatically opens the form with the photo in a rounded frame and
   drink type/size underneath. Retake clears the pending capture and returns
   to full-screen camera; Close returns to Lobby without saving. There is
   no upload until Submit and no gallery upload. The location is the phone's
   GPS reading at submission (R-L01), accepted if it is off by at most
   50 m (R-L02).
3. App shows the detected territory and scoring preview: base points,
   additional prior-owner income if applicable, and estimated awarded points.
4. Player submits. Server validates required inputs, location evidence,
   eligibility and duplicate protection using agreed rules.
5. If accepted, server saves the check-in and calculated points. An eligible
   entry outside all territories contributes to the season leaderboard. An
   eligible entry inside a territory also contributes to that territory.
   The app shows points awarded and any ownership change, with links to Map
   and Standings. Each new entry requires a fresh photo.
   Check-in success shows “You captured <territory>!” when that saved entry
   first claims an unowned territory or strictly overtakes its prior owner.
   It uses the saved season history in acceptance order through that entry,
   including when recovering a lost successful reply. A tie, defending one's
   own territory, an outside entry or a rejected submission shows no capture
   message. Later entries do not rewrite the historical capture message;
   Map and Leaderboard in bottom navigation lead to the latest standings. If the feedback
   lookup fails, the saved-points confirmation remains and no save is retried.
6. If rejected, no points change. Explain why and offer a relevant retry.
   If location is missing or uncertain, the player keeps the drink selection
   and photo on the form and tries location verification again.
   If the network result is uncertain, retrieve the submission status before
   retrying; do not create a second award.

The preview is an estimate until accepted: another player may change
ownership before submission. Exact modifier timing needs team agreement.
Photo/location failures must never be represented as a successful check-in.

### Save and view a check-in photo

The photo storage integration should save the file in a private Supabase
bucket and record its storage path on the drink entry. When someone opens
the photo, the server checks that their signed-in account currently belongs
to the lobby where the entry was logged and satisfies R6/R-PH01 consent
before serving the image. The gallery applies the same rule. For older
entries with placeholder references, the app shows that the photo is
unavailable.

In Profile → Account & security → Photo privacy, the player saves one
account-wide sharing toggle, initially OFF even for existing accounts.
It affects existing and future photos. Own photos remain available under
R7; other players' cards appear only when sharing permits it. In team mode,
current teammates can view their saved team's photos internally even with
sharing OFF. Opponents need consent from the uploader and all current
members of that saved team. A new member with OFF withdraws opponent
access to historical photos too. Chug Duel copies follow their respective
owners independently. Each card and detail image has an identity-coloured
frame and username, plus the saved team's name in team mode.

Check-in records when the app receives the camera photo separately from
when the player submits the entry. The photo view shows this capture time,
the submitter's username, and the verified territory name or “Outside game
territories.” Photo GPS tags are not used (R-L01); remove the embedded
metadata before saving the image. Save the verification result and
territory match from the location check. Discard the exact phone
coordinates after verification.

The camera upload accepts JPEG images up to 10 MiB and 20 million pixels.
These server resource limits are checked before decoding image pixels.

The photo's owner can select it in Lobby photos and confirm deletion. The
server verifies ownership again, removes the private file, and marks its
reference `deleted`. The drink entry, awarded points and standings remain.
Other lobby members cannot delete it. A downloaded copy or screenshot cannot
be recalled from another player's device.

Photos stop being served at exactly 30 days after the season's end. The
server maintenance command `python -m data.cleanup_checkin_photos --apply`
removes expired files and marks their references `expired`. It also removes
unlinked uploads that have had no update for 24 hours, allowing time to retry
a failed database save. It never deletes entries or changes points. The Data
owner must schedule this command and monitor successful runs. Access expiry
works even if a cleanup run is delayed; physical deletion needs that job.

### Duplicate check-ins in the current build

Check-in records a time-zone offset and compares new and saved submission
times in UTC. If a lobby member submits the same drink type within two
minutes of a saved entry, the page shows “You already logged this drink a
moment ago.” The app saves no second entry and awards zero extra points.
At exactly two minutes, the submission can continue through the other checks.

The final repeat-drink and duplicate rules are still open under D-12.

### Proposed fallback after automatic location verification fails

If the automatic check using phone GPS fails, the
player can share a one-time confirmation link with another member of the
same lobby who was there. The recipient signs in and confirms they were
present. The server checks their lobby membership and uses the link once
for a successful confirmation. The request expires 24 hours after the
original check-in or when that season ends, whichever comes first. A
decline closes the request immediately.

Pending, declined, and expired requests earn zero points. If the entry
meets the other scoring rules, a confirmation awards season points once.
The entry has no territory assignment. For a tie in the season standings,
the points count from the moment the other player confirms.

## Proposed scoring workflow - review pending

The [canonical proposal](SCORING_PROPOSAL.md) defines the replacement flow: four quick categories and size presets (P-S01-P-S04); full drinker awards plus separate 25% owner season income (P-S05-P-S08); weekly eligibility (P-S09); a shared two-minute posting cooldown and idempotent retries (P-S10/P-S11); and two-minute corrections with downstream replay (P-S12). This is not the behaviour of the current prototype. Photo deletion and retention remain governed by R7/P-S15. The [acceptance matrix](SCORING_PROPOSAL.md#13--outstanding-approvals-and-acceptance-checklist) covers allowed, rejected and boundary cases.


## Remember the selected lobby (18 November 2026)

Contributor decision: the last lobby explicitly chosen as the context for
lobby-specific pages is saved per player in the database, across devices,
logouts and app restarts. Opening a joined lobby card or successfully
creating/joining a lobby selects it. Closing its popup and refreshing the
Lobby page keep that selection. Automatic selection never overwrites the
player's explicit saved choice, and restoration never reopens a popup.

After authentication, restore the saved lobby before rendering Leaderboard,
Map, Check-in, Minigames or Photo history. Recheck current membership and load
current lobby mode, team and season from the database. A preference grants
no access. If membership has been removed, require a choice on the Lobby page.
If the saved competition has finished, select the newest active competition
(by start timestamp, then lobby ID). With no active alternative, require a
choice; finished results remain available by opening their lobby explicitly.
A player without a saved choice also defaults to their newest active lobby.
Upcoming/incomplete saved lobbies stay selected; existing workflow checks
explain when a season or team is still needed.

Leaderboard can display standings even when the shared selection has no usable
season. It shows the newest active competition the player belongs to if one
exists. Otherwise it shows the saved lobby's season if the player still belongs
to it, or the season of the most recently joined lobby with a season. It labels
finished standings and links to Lobby if there is nothing to show. This
display-only fallback checks membership and leaves the gameplay lobby and
the saved choice unchanged.

The same running session keeps its own context when another device changes
the account preference. Reopening restores the latest successfully saved
explicit choice. A failed preference write leaves the lobby usable for the
current visit and shows a retry message. A failed restoration is retried on
the next page load; existing access checks still apply.

## Leave or return to a lobby

1. Open Lobby, then View lobby → in an individual or team lobby.
2. Choose Leave lobby. Review the explanation that scores and the reserved team
   slot remain, while access and personal owner income pause.
3. Choose Stay in lobby to cancel, or Confirm leave. The database rechecks the
   actor and expires stale games under the same lock used by scoring. Active
   accepted/started duels and running Focus attempts reject departure.
4. On success the popup closes, the lobby card disappears and a success notice
   confirms retained points. Another active lobby may become selected. Profile
   statistics still load the departed membership and its full scoring history.
5. To return, use Join with a code and the original invite code. The original
   membership, team and limits resume. A finished competition stays finished.

Service errors keep the lobby open with an error and a refresh instruction;
a retry is safe when the original response was lost. Active membership checks
on pages, photo reads and game RPCs revoke access from other open sessions too.
