# Minigames proposal

19 November follow-up: the current solo-game discussion is recorded in
[FOCUS_CHALLENGE_PROPOSAL.md](FOCUS_CHALLENGE_PROPOSAL.md), including the
contributor's five-check-in and temporary multiplier ideas. The earlier
recommendations below are historical; neither draft creates active rules.

Superseded for Chug Duel by the contributor's explicit answers on
18 November 2026: see RULES.md R-M01–R-M05 and [CHUG_DUEL.md](../CHUG_DUEL.md).
The recommendations below preserve the earlier discussion, including the
alternative games. They do not restrict the subsequently authorised duel.

Discussion draft, 18 November 2026. This records the contributor's request
and proposed designs, not implemented rules. GAME.md and RULES.md remain the
current contract. No scoring, shared models or database behavior changes here.

## Requested experience

- One minigame per player per evening, shared across all game types.
- Challenge another player and record a winner, with a reward or effect.
- A reaction game that becomes available later in the evening.
- More games connecting people meeting in real life with the app.

The contributor suggested a drinking-speed contest, alternative rewards
(points, a loser penalty or a winner effect), and reaction-game access after
elapsed time or five photo posts. These are alternatives for discussion.
The recommendation below uses skill contests, elapsed time and items, keeping
the existing no-direct-minigame-points rule.

## Recommended shared flow

1. Show available games, unlock times and whether the evening's play remains.
2. For a duel, invite a member of the same active lobby. Show rules and rewards
   before acceptance. Declining or an expired invitation uses neither slot.
3. On acceptance, reserve both players' slots together, or neither if one is
   unavailable. A solo game reserves its player's slot on start.
4. Complete the task and show the recorded outcome. Give the winner one item;
   the loser keeps their points. A solo success gives one item.
5. Refreshing or retrying returns the same attempt and cannot give another
   reward. A reconnect resumes the attempt rather than starting a fresh one.

Recommended night rollover: 06:00 in the agreed game timezone. For example,
Friday 23:30 and Saturday 02:00 belong to the same Friday night; Saturday
06:00 belongs to the next allowance. Also require an active season and its
open play window; a rollover never opens play outside that window. Exact
hours, timezone and whether the allowance follows a player across lobbies
need shared-model review before implementation.

Recommended interruption policy: a started game uses the slot. Resume it after
a connection loss; an abandoned or disputed result gives no reward. A failure
before the server commits the start uses no slot. Result deadlines and what
happens at night/season end remain to be agreed.

## Games

All numbers below are suggested defaults, not active rules. All rewarded
games use the same evening allowance, including games that unlock later.

| Game | Real-life task | App role and result | Priority |
| --- | --- | --- | --- |
| Reaction duel | Two people together each take five timed reaction trials on the same phone, passing it between turns. No drink or drinking-speed task is required. | Random wait before the signal; early taps invalidate a trial. Lower median reaction time wins; equal medians draw. A draw gives no item and still uses both slots. | First playable game: solo mode first, duel next. |
| Late-night reflex | A solo five-trial reaction game available two hours after that player's first accepted check-in of the same night and lobby. | Show the exact unlock time. Compare the median with a target shown before starting; choose and test the target before implementation. Present it as a reaction game, without a sobriety or driving-fitness verdict. | Reuse the reaction component. |
| Cup toss | Two players take five throws each at empty cups, or cups containing water, from the same marked line. | Both confirm the hit totals and winner. Equal scores draw; conflicting reports give no reward. | Simple physical duel; results are trust-based. |
| Photo mission | Find a public detail from a prompt, such as a mural or a specific colour, and photograph it without requiring a drink purchase or post. | Display the prompt and collect a fresh mission photo. A non-participating lobby member confirms it; no automatic object recognition is claimed. | Later: needs photo access/deletion rules and a reviewer. |
| Pantomime | One player acts out an app-selected word for another person to guess within 30 seconds. | Reveal the word privately, run a timer, then have both confirm success. Only the actor uses a slot and receives a success item; the guesser is an unpaid helper. | Later: simple social game, trust-based. |
| Memory table | A friend arranges five ordinary objects; the player looks for ten seconds, turns away, then recalls the objects. | Guide the setup and timer. The helper records the initial list and confirms the answers. Only the guessing player uses a slot and can earn an item. | Later: no map or scoring changes needed. |

For Late-night reflex, no first accepted check-in means no unlock countdown.
Use the server's accepted-entry timestamp, not photo metadata or the phone's
clock. Exactly two hours is eligible, just before is not. Five posts do not
provide an earlier unlock. Use entry records, so deleting an image does not
reset the clock. A player who already used their slot cannot play again when
the reaction game unlocks; show this before they choose their first game.

Do not implement the proposed drinking-speed contest or a reward for reaching
five drink posts. The alternative games provide the face-to-face competition
without making additional consumption part of winning or unlocking play.

## Rewards and effects

Recommended first reward: a winner crown on the lobby profile for the rest of
the game night. A solo success earns a challenge badge for the same duration.
Award each at most once per completed attempt. These are visible effects and
do not alter season totals, territory accounts or ownership.

Later cosmetic items could include a profile frame or a victory animation.
Optional loser forfeits should require acceptance before starting and be
cosmetic, such as a temporary nickname selected from predefined choices.

Strategic ideas such as territory shields, stealing points, multipliers or
deducting the loser's score require a separate scoring/ownership decision.
Before implementing them, define target, duration, expiry, stacking, team
behavior and replay/correction interactions. Direct minigame points would
change the existing contract and need an explicit team decision.

## Current implementation and review needs

- `core/minigames.py` counts attempts by membership and supplied window ID.
  It has no playable game, unlock logic or reward issuance.
- `core/game_window.py` currently supplies a weekly Thursday ID, not nightly
  IDs. Merely adding a minigame screen would not implement the evening rule.
- `data/db.py` currently reads/inserts attempts. Concurrent reservations,
  two-player challenges and exactly-once rewards need database enforcement.
- `MinigameAttempt` describes one member's attempt. A duel needs a reviewed
  link between both participants and their common outcome. Reward items are
  still candidate entities in ENTITIES.md.
- Physical-game confirmations are trust-based. GPS can establish location
  evidence but cannot establish who won a throw or acted out a word.
- Game timers need a browser component; Streamlit reruns and network latency
  must not be used as reaction-time measurements. Client measurements remain
  tamperable; review that limit before attaching valuable rewards.

Related decisions: D-04 (items), D-05 (night boundaries), D-07 (interruptions),
D-18 (game selection and unlocks), D-19 (allowance scope and duel records).

## Delivery and expected checks

Finish and verify the core check-in/scoring workflow first, as AGENTS.md
requires. Then implement one solo reaction game with the shared nightly
limit and cosmetic reward; add duels and one physical game after that works.

Before implementation, settle the shared scope/timezone, reservation and
expiry rules, first-game success target and reward persistence with the team.
Use the same rules for UI availability and server validation.

| Case | Expected outcome under the proposal |
| --- | --- |
| First eligible start | One saved attempt and one reserved allowance. |
| Second start, including another game or device | Rejected; no extra attempt, item or points. |
| Two simultaneous starts | At most one succeeds for each player. |
| Duel accepted when either participant has played | Neither participant gets a new reservation. |
| Invitation declined or expired before acceptance | Both allowances remain available. |
| Result submitted again or refresh after success | Same outcome; no second reward. |
| Reaction game at first accepted entry + 1:59:59 / + 2:00:00 | Locked / unlocked, if all other eligibility checks pass. |
| Several photo posts before two hours | Reaction game stays locked. |
| Midnight / 06:00 rollover | Midnight keeps the allowance; 06:00 changes the night ID. |
| Season ended, window closed, or no lobby membership | Start rejected; points unchanged. |
| Client-supplied earlier time or forged participant | Server rejects the eligibility or unauthorized action. |
| Disputed physical-game result | No item; started slots remain used. |
| App restart after starting or receiving a reward | Attempt, used allowance and reward remain saved. |

For this documentation change, review links and the existing minigame tests.
No new gameplay, browser behavior or database persistence is claimed tested.
