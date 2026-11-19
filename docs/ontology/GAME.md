# Game

Working scoring v1 was authorised by the contributor on 17 November 2026.
It is implemented on `Scoring`, with teammate review, shared migration and
live verification pending. [SCORING_V1.md](SCORING_V1.md) is the current scoring
contract; [the planning record](SCORING_PROPOSAL.md) preserves the discussion.
Existing legacy seasons retain their original rules and historical points.

## Goal and accounts

Players compete in lobbies: groups joined using the same invite code. Each
lobby runs its own season. Its length is chosen when the lobby is created:
one week, one month or three months ([R-R02](RULES.md#r-r02-season-length)).

Individual is the default competition mode. The highest player total wins
there; team lobbies instead combine members' points and award the win to the
highest team total. Teams also combine territory base points for ownership.
The creator chooses team count, capacity and random/manual assignment;
members can edit their team's name and picture (R-TEAM01–R-TEAM05). Ties favour whoever reached the tied score first
([R-R01](RULES.md#r-r01-ties)).
An individual player's season account combines their own base awards and
additional territory-owner income. In team mode, the team has the combined
account. Each territory has a separate account per competitor (player or
team), containing only that competitor's base awards there. Owner income never affects
territory ownership. Cross-lobby/lifetime rankings are outside this version.

## Drink entry and base points

Use Beer, Wine, Shot and Mixed drink (cocktails/long drinks together). Beer and
wine show defined Small/Medium/Large volumes; mixed sizes are trusted labels.
A Shot uses one serving without a size step. The fixed 1-5 table and its
embedded Large bonuses are defined in [SCORING_V1.md](SCORING_V1.md).

A fresh photo and accepted location evidence are required. A matched entry
credits the drinker fully in season and territory. A verified outside entry
credits the season only. Only the phone's GPS counts, accurate to 50 m; the
measured point decides at borders (R-L01–R-L03). Exact GPS is discarded after checking;
the photo is stripped of embedded metadata and shared only within its lobby.

## Weekly eligibility and limits

New v1 scoring runs continuously from Thursday 18:00 inclusive to Sunday
18:00 exclusive in the lobby season's chosen timezone, during the season's
own start/end boundaries. The database scoring-request receipt time is
authoritative. New entries are blocked outside the window. There is no fixed
nightly count, but accepted entries share a two-minute cooldown per player
and lobby across all categories. Retries return their original result once.

## Territories and owner income

Territories are predefined map areas; bars are not part of scoring. The
location assigns the territory. The shared file contains 48 bordering areas from Alfama to Carcavelos (small ones in the centre, large ones on the way to Nova SBE),
with permanent IDs and non-overlapping interiors (R-T01/R-T02).

The highest territory total owns it, with earliest-reached ties. Reward the
owner immediately before each accepted entry, then update ownership. A
different prior owner receives an additional 25% of its base award in season
points only. The visitor loses nothing. No self-income or fixed income cap.
Use exact quarter-points. First positive entries claim an unowned territory
without a first-owner bonus. New season IDs reset standings without deleting
old history. Exact ordering/defaults are documented in the v1 contract.

## Corrections and stable seasons

An author can correct drink/size for two minutes, before season end. Record
the revision and replay affected ownership and subsequent owner income from
the original event position. An image deletion keeps points. The season's
settings/timezone/dates are frozen; changes start in a new lobby’s competition (R-R03).

The inherited season choices remain 7, 30 and 91 elapsed days. Calendar-month
semantics, host roles and leaving/absence workflows remain team review items.
Phone GPS is followed automatically; accuracy, borders and reading age are
decided (R-L01–R-L04).
Friend confirmation remains a separate proposal, not an active v1 fallback.

## Minigames

Chug Duel is the first playable minigame, authorised by the contributor on
18 November 2026. In normal seasons each player can challenge once and accept
once per lobby and night, with a 06:00 rollover in the season timezone. Explicit QA/test seasons
instead allow unlimited sequential replays, with all normal check-in evidence,
cooldown and scoring rules still enforced (R-M02). An opponent accepts
the selected drink and size on their own device. The challenger takes one
shared photo and provides the shared verified location, then hosts a
split-screen board. Both players press Ready; after a countdown the first
finish tap wins. Physical completion remains trust-based.

The winner receives both drinks' base season points; the loser receives zero
base season points from that duel. Both retain normal territory base points,
and owner income remains normal. Before a result, or after a started abort,
each keeps their normal drink award. Team duels require different teams.
This explicitly supersedes the items-only/shared-one-play rule for Chug Duel;
future games, items and stacking remain separate decisions. See
[R-M01–R-M05](RULES.md#minigames) and [the handoff](../CHUG_DUEL.md).

[MINIGAMES_PROPOSAL.md](MINIGAMES_PROPOSAL.md) records the 18 November request
for duels, a delayed reaction game and real-life/app challenges, with suggested
flows and rewards. It is a historical discussion draft; Chug Duel's later
decisions above supersede its recommendations. Other proposed games remain
unimplemented.
