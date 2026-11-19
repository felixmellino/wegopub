# Quiz Duel rules

Contributor decisions, 19 November 2026. Implemented and merged through PR #60;
shared Supabase migration 016 was installed on 19 November 2026. All four
installation checks and app-server Quiz status in 13 v1 seasons passed.
Full deployed two-player gameplay remains to verify; the rule decisions below
were not changed by database activation. See the [handoff](../QUIZ_DUEL.md).

## Agreed rules

- A lobby member challenges another player, who accepts on their own account.
- Each round gives one quiz point to the faster correct answer. Incorrect answers
  do not earn a point. Each player receives the same question and four choices.
- Normal order: general knowledge, multiplication, logic. There are up to three
  normal rounds. A 2:0 ends the game early.
- If tied after three rounds, play up to three additional general-knowledge
  deciding questions. The first round winner wins the duel; otherwise draw.
- Each question lasts 20 seconds. Each player submits one locked answer.
  Both wrong/missing or exactly equal server receipt times give no round point.
- After three normal rounds, the higher score wins even if below two points.
- The challenger proposes an integer stake from 3 to 10 season points, visible
  before acceptance. The winner receives that stake from the loser; quiz points
  only determine the duel winner. Territory points/owner income are unaffected.
- Quiz has its own normal allowance: one outgoing challenge and one acceptance
  per member/lobby/night, independently of Chug Duel. Reuse the season-zone
  06:00 rollover. Explicit test seasons allow unlimited sequential quizzes.

Both sides must have the full available stake. Acceptance reserves both stakes.
Reservations also cover other members spending from the same team purse; the
same points cannot fund overlapping bets. No negative balances. Drink corrections
that would remove committed or already-spent points are rejected atomically.
In team lobbies only opposing teams may play; the transfer changes team scores.
Individual quiz transfers count in personal lifetime points; team transfers
do not become personal drink points. Completed-season wins include transfers.

The earlier items-only proposal is superseded for Quiz Duel by this explicit
stake decision. Chug Duel and Focus keep their existing independent rules.

## Content foundation

- 100 source-linked English general-knowledge questions are checked into the repo.
- The contributor's revised content target is easy/easy-medium: 20% football,
  80% broader general knowledge. Football events/transfers refer to 2022 onward;
  stable club facts may be undated. Detailed census and older niche sports
  questions were removed.
- Multiplication is generated from factors 1–10, not individually authored.
- Logic uses five short templates by default; a sixth, longer box puzzle is an
  explicit advanced preview option. Names and values vary.
- Private snapshots preserve both the question and the answer order across devices
  and reloads; player payloads exclude the answer key.
- A fresh general-knowledge decider can be generated without repeating a question.

See [the preparation handoff](../QUIZ_QUESTION_PREPARATION.md) for code and verification.

## Lifecycle and operational defaults

- Each player readies on their own phone; the second ready starts a three-second
  countdown. One fixed board shows countdown, question, answers and result.
- A three-second result interval precedes each next countdown.
- Invitation and accepted setup expire after ten minutes each. Before starting,
  either participant may cancel an accepted game, releasing stakes and allowances.
- After the common start, explicit forfeit transfers the stake to the opponent.
  Refreshing, navigating away and losing connection do not emit a forfeit.
- Reload restores the saved deck, answer locks and deadlines. Time continues.
  Unanswered elapsed rounds resolve on recovery. Both absent produces a draw
  after all six questions, without transferring points.
- Deadlines are capped at season end, next local 06:00 and the scoring-window end
  (normal seasons). An incomplete question at that boundary is void: draw/refund.
  Started games still consume their two respective role allowances.
- Normal seasons use the scoring window; explicit QA seasons may play any time
  while active. QA removes nightly role limits, but still requires funded stakes.
- Only one accepted/running minigame per participant; an open invitation does
  not block playing. Team changes are blocked while a stake is reserved.
- Fastest means PostgreSQL receipt time, including network delay. Client timers,
  reported winners and claimed correctness never decide the result.

The contributor confirmed funds, team purse, forfeits, twenty seconds and the
three-decider cap in this chat. The phase durations/expiry above are documented
implementation defaults. See [implementation](../QUIZ_DUEL.md) for verification.
