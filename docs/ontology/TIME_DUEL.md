# Time Duel

Contributor decisions, 19 November 2026. Implementation on the Time Duel branch;
shared migration 017 was applied on 19 November 2026. Teammate review and
app deployment remain pending.

## Agreed gameplay

Two active members in the same lobby play on their own accounts/phones. Team
lobbies use opposing teams, consistent with the other duels. Each of three rounds
has a server-generated whole-second target from 5 through 12 seconds, identical
for both players and revealed only when both have readied for that round.
Each player taps Start and Stop independently. The running timer is hidden.
Intervals use the phone's monotonic clock, rounded to integer milliseconds.
The player's result appears immediately after Stop. The opponent's measured time
is disclosed only once the viewer has started their own timer. Future targets
and unrevealed results never cross the browser bridge.

Compare abandoned-round counts first (fewer wins), then the sum of absolute
millisecond errors over each player's valid rounds (smaller wins). No early win:
resolve all three rounds. Leaving/reloading while timing abandons that round;
a submitted Stop retries its existing result rather than starting again.
An exact total-error tie rewards both only when all six individual rounds were
valid. A tied incomplete duel grants neither player a bonus.

## Reward and scoring

The winner automatically receives x1.25 on personal season points from future
ordinary check-ins for one hour. Territory points, territory ownership and owner
income are unchanged by Time Duel. It does not boost Chug/Quiz transfers or
lifetime points. In team mode the successful player's own check-in contribution
adds to their team season total; teammates do not inherit the effect.

Only the highest active multiplier applies: Focus x1.5 retains its existing
season/territory/owner effects, suppressing Time Duel while Focus is active.
Each reward keeps its own interval; nothing stacks or queues. Multiple Time Duel
wins give overlapping one-hour intervals, not added durations. Receipt time is
authoritative: start <= receipt < expiry. Ordinary entries snapshot Time Duel
provenance and a separate season bonus; corrections recalculate from the original
snapshot, never current bonuses. Photo deletion preserves the award.

## Lifecycle defaults

Invitation flow, contributor decisions 19 November 2026: incoming Time Duel
invitations appear directly above the Minigames catalogue tiles with Accept and
Decline. The sender sees a **Pending Challenge invite** box, the recipient,
remaining time and Cancel. One pending outgoing invitation blocks another send
to any player, including from another tab or after reconnecting. Multiple
incoming invitations are allowed. When there is more than one, Accept first
shows "If you accept this invite, the other invites for this minigame will be
declined." and requires Confirm acceptance; Keep invitations backs out.
Acceptance atomically declines both participants' other incoming Time Duel
invitations and cancels their pending outgoing Time Duel invitations. Unrelated
invitations and invitations for other games are unchanged. Neither participant
can send or accept another Time Duel while their accepted/running duel remains
open, including in QA seasons. Acceptance opens the existing two-phone Ready
flow. No allowance is consumed by declined, cancelled or expired invitations.
Migration 021 enforces these rules under the existing lobby transaction lock.

Time Duel has independent one-outgoing and one-incoming allowances per member,
lobby and 06:00-based season-timezone evening. Acceptance reserves the roles;
the first shared round reveal consumes them. Pre-start cancellation or expiry
releases the reservation. Explicit JSON test_mode=true allows unlimited
sequential games while the season is active, with no drink/upload unlock.
Normal games require the season scoring window. Existing v1 seasons are supported;
no frozen scoring snapshot is edited. Legacy seasons remain unavailable.

Only one accepted/running minigame per member at a time. Accepted/running Time
Duels block team changes and lobby departure. Invitations expire after ten minutes;
the accepted duel has a ten-minute overall ceiling. Ready and play phases have
60 seconds each; a running timer has 30 seconds. Expired responses abandon a
round; an overall/night/scoring/season cutoff ends the duel without a reward.
Rewards end at scoring closure or season end (QA: season end), and may cross 06:00.
Timing evidence is honour based; external clocks and modified clients cannot be
reliably prevented. The database validates participants, phases, evidence bounds,
first-result locks, allowance reservations and exactly-once rewards.

## Verification and activation

See [the implementation handoff](../TIME_DUEL.md). Apply migration 017 only after
015, 016_quiz_duel and 016_leave_lobby. Shared scoring/model integration requires
teammate review under the project workflow before merge. The shared migration checks are recorded in the handoff.
