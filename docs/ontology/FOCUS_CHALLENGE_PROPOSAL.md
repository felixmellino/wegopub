# Focus Challenge — approved design, 19 November 2026

The contributor confirmed teammate approval and requested full implementation
on 19 November 2026. Implemented rules are R-M06–R-M09 in RULES.md; setup and
verification live in [FOCUS_CHALLENGE.md](../FOCUS_CHALLENGE.md). Migration 014
is prepared and isolated tests pass; shared-project application and real-phone
calibration remain pending. The discussion record below preserves the choices
and earlier open points; implemented defaults supersede its open-point list.

## Contributor's requested idea

- Make several games visible together on the Minigames page.
- Add a solo challenge after five accepted drink entries in one lobby
  evening, regardless of drink type or size. The player's shared Chug Duel
  entry counts once; retakes, duplicate retries and rejected submissions
  do not count.
- Use the same evening boundaries and open scoring window as Chug Duel.
  The existing night resets at 06:00 in the season's frozen lobby timezone;
  after-midnight entries before 06:00 belong to the preceding evening.
- Pass three challenging tests consecutively.
- Contributor selected a 1.5 multiplier on subsequent ordinary check-in
  season and territory points for 60 minutes. Owner income uses the boosted
  award. Chug Duel entries and transfers retain their existing scoring.

## Contributor selections — 19 November 2026

Working name: Focus Challenge. The contributor selected reaction, memory
sequence and precision tapping, passed consecutively in one run. It is an
entertainment skill game, not a sobriety assessment or permission to ride/drive.
A pass means only that the player completed the game's tasks.

1. Reaction: wait through a random delay, then tap a target. Early taps fail
   the stage. Five trials; the median must be at most 350 milliseconds.
2. Memory: briefly show a seven-position sequence, then reproduce it exactly
   in order.
3. Precision: twelve correct target taps within twelve seconds, with no wrong
   targets. Shapes/numbers should make it usable without colour matching.

These are the contributor-selected harder pilot settings. Target sizes,
reaction random-delay ranges, memory display/input timing and decoy behavior
still need an implementation proposal. Pilot on ordinary iPhone and Android
devices before calling the difficulty balanced. Measure timing in the browser with
a monotonic clock, not network latency. No camera/GPS access or motion sensor
is needed for these tasks.

The contributor rejected timed retries: one attempt unlocks after five
check-ins; failing that attempt unlocks another after seven check-ins in
the same evening. Every attempt requires passing all three games in a row.
After each failure, another attempt unlocks with two additional check-ins:
5, 7, 9, 11, and so on. The contributor selected one successful reward per
evening. On success, the 1.5 multiplier activates automatically for 60 minutes
on future eligible drink season/territory awards; the owner's 25% income is
based on the boosted drink award as well. Attempts and reward are implemented on the feature branch. Focus attempts have their own allowance, separate from
Chug Duel's challenge and acceptance limits. Chug Duel entries count toward
Focus unlocks, but do not receive the Focus multiplier.

An interruption resumes the same attempt and its clock keeps running. A
refresh, app switch or disconnect does not grant a fresh attempt at the same
threshold. Define the precise per-stage deadlines and reconnect protocol
before implementation.

In a team lobby only the successful player's ordinary entries are boosted;
their awards contribute to their team's season and territory totals as usual.
Teammates' own entries are not boosted. A boost earned before 06:00 keeps its
full 60-minute duration across that reset. It never stacks above 1.5, and
normal scoring/season closure still prevents check-ins from earning points.

## Fresh variation on every new attempt

Contributor requirement, 19 November 2026: repeated play on the same evening
or across days/weeks must not offer a fixed sequence players can memorise.
The three stage types and their pass thresholds stay consistent; their
content changes. Learning the controls and improving genuine skill is fine.
Randomisation is not a guarantee that chance repetitions can never occur.

- Reaction: sample a new unpredictable waiting time independently for each
  of the five trials. Do not use a repeating delay cycle, an increasing-delay
  pattern, or the same timing sequence for everyone on a given date. Keep
  the signal and tap interaction consistent so randomisation does not change
  what the 350 ms target measures. Set bounded wait times during prototyping.
- Memory: generate a fresh seven-position sequence for each attempt from
  the same fixed grid. Positions may recur later in a sequence, but avoid
  adjacent repeats that would make two flashes look like one. Do not select
  from a small bank of predefined sequences. Grid dimensions and timing are
  still prototype details.
- Precision: sample fresh valid target positions and any decoy arrangement
  for each of the twelve steps. Avoid fixed routes, predictable corner
  rotations, clipped targets and nearly identical consecutive positions.
  Keep the target sizes, spacing constraints and twelve-second budget
  consistent across players and adapt the play area to the phone viewport.

For the later implementation, generate one cryptographically random challenge
seed/material on the server for each genuinely new attempt. Do not seed from
a player's identity, the calendar date, the attempt number or the phone clock.
Persist that attempt's generated challenge and progress with its deadlines.
Refreshing, reconnecting or opening another tab must recover the same
challenge, not reroll content or reset its clock. A retry at the next eligible
check-in threshold receives new challenge material.

Send only the stage content the client needs; do not unnecessarily reveal
future sequences or expected answers up front. This reduces casual inspection
but does not make browser-measured skill tasks tamper-proof. The server still
validates attempt identity, permitted transitions and one-time reward issuance.

Verification must use controlled random sources to test different challenges
for different attempts, stable content/deadlines when resuming one attempt,
valid sequence/position constraints, unchanged difficulty thresholds and
rejection of another attempt's results. Avoid flaky tests that depend on two
random samples happening to differ. Repeated phone play should check that
there is no visible recurring route or timing pattern before release.

## Earlier implementation questions (resolved by R-M06–R-M09 unless noted)

- Confirm whether deleting a photo leaves its original accepted-entry count
  intact (recommended, consistent with score preservation under R7).
- Confirm whether QA/test seasons bypass the count gate. Existing Chug Duel
  QA exceptions do not silently decide this new game's rules.
- Specify target sizes, random delays, memory timing and stage deadlines;
  test the selected 350 ms / seven-step / twelve-target difficulty on phones.
- Specify persisted progress for a resumed attempt, its overall expiry,
  06:00 attempt rollover and season/window-closing behavior. Boost carry-over
  at 06:00 is selected above; attempt carry-over remains open.
- Preserve the selected 1.5 multiplier, automatic activation, 60-minute
  duration and one successful reward per evening. Define overlapping night
  rewards without exceeding 1.5; simultaneous tabs cannot issue a second boost.
- Owner income uses 25% of the boosted drink award (contributor selected).
  Ordinary check-ins alone receive the boost; Chug Duel entry and transfer
  scoring remain unchanged. Team totals receive the successful member's
  boosted awards; teammates' other entries keep their usual awards.
- Set exact start/end boundaries using server receipt time, including an
  entry at expiry, an upload begun earlier, and season/window closure.
- Upgrade precision without rounding away the selected owner income: a
  boosted 1-point drink is 1.5; 25% of that is 0.375. Exact eighth-point units
  can represent both awards; the existing owner-income quarter units cannot.
- Decide how boosted entries interact with corrections, historical ownership
  replay, ties and the permanent audit trail after the effect expires.
- Have the Scoring/Data/Location owners review shared models and contracts
  before implementation. Existing active seasons have frozen rules.

## Security and verification requirements for the later implementation

The server must enforce membership, eligibility count, attempt reservation,
expiry and one-time reward issuance atomically. Refreshing or using two tabs
must recover the same attempt, not create another reward. The client cannot
submit a trusted points multiplier. Browser timings/results remain tamperable;
agree how much trust is appropriate before attaching valuable score effects.
Store only necessary game events/results, not a health or sobriety label.

Tests should cover eligibility immediately before/at the threshold and 06:00,
other-lobby isolation, duplicates, deleted photos, duel entries, failed or
interrupted rounds, concurrent starts/rewards, reward expiry, scoring closure,
corrections/replay, team mode and restart persistence.

Research: [Bolt describes its scooter reaction test](https://bolt.eu/en/support/articles/14528/)
as responding to a visual prompt. This is inspiration for interaction design,
not evidence that a WeGoPub score can establish sobriety or riding fitness.
