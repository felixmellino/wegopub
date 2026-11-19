# Scoring v1: implemented working rules

Focus Challenge extension, team-approved 19 November 2026: R-M06–R-M09 add
frozen rules to new seasons and an automatic x1.5 ordinary-check-in effect.
Owner income uses the boosted award. Numeric awards support half-points and
half-quarter income units (exact eighth-points); display up to three decimals.
A saved `focus_attempt_id` preserves the multiplier through expiry/corrections.
Existing seasons and Chug Duel scoring are unchanged. See
[the implementation](../FOCUS_CHALLENGE.md) and migration 014.

Status: implementation authorised by the Drink Entries & Scoring contributor
on 17 November 2026. Implemented locally on `Scoring`; teammate PR review,
shared migration and live verification are pending. The [implementation and
Data handoff](../SCORING_IMPLEMENTATION.md) names the files, defaults and checks.
The [planning record](SCORING_PROPOSAL.md) retains the conversation decision IDs.

## P-S01-P-S04: drink selection and base table

Use four category buttons. Beer, wine and mixed drinks have Small / Medium /
Large. Shots have one serving with no size control. Mixed sizes are selected
honestly; photos support lobby review rather than exact recipe measurement.

| Category | Small | Medium | Large |
| --- | --- | --- | --- |
| Beer: 250 / 330 / 500 ml | 1 | 2 | 3 |
| Wine: 100 / 150 / 250 ml | 1 | 2 | 4 |
| Mixed drink: selected size | 2 | 3 | 5 |
| Shot: one serving | 4 | Not applicable | Not applicable |

The Large bonus is already included. Do not add it twice. The UI uses frozen
volume definitions and an automatic preview, with no free-form point input.
Cocktails/long drinks share `mixed` in v1; historical `longdrink` rows remain
legacy. The actual table and settings are defined in `core/scoring_v1.py` and
copied into the season's rules snapshot for UI, Python and SQL validation.

## P-S05-P-S08: accounts, ownership and ties

The drinker keeps all base points in the season and matched territory. A
verified outside entry earns season points only. No cap is applied to the
number of accepted entries or to ownership income.

The previous owner receives an additional 25% of another member's base award,
in season points only. No visitor deductions, self-income, income-on-income
or bonus territory points. Keep exact quarters: base 1/2/3/4/5 produces owner
income 0.25/0.50/0.75/1/1.25. Owner income never claims/defends territory.

For each accepted event: inspect prior owner, award the drinker and any owner
income, then update territory totals. A capturing event rewards the outgoing
owner. Territory and season ties favour earliest arrival at the tied total.
New seasons begin unclaimed; the first positive matched entry claims without
income on that first entry. Accepted writes receive a database event order.
For a genuinely same-event season tie, the previously higher-ranked owner
keeps precedence. These initial/exact-tie defaults are explicit implementation
choices for teammate review.

## P-S09: eligibility and the shared clock

The weekly window is continuous Thursday 18:00 inclusive through Sunday
18:00 exclusive, in the season's named lobby timezone. Also require
`starts_at <= submission < ends_at`. The database scoring-RPC receipt time
is authoritative; photo receipt and phone time do not backdate a submission.
The UI preview is rechecked after upload. Outside the window/season, block
new entries, save no points and show the next opening where one exists.

Explicit QA seasons may opt into Wednesday 08:00–Sunday 18:00 instead.
The selected `test_mode=true`, start weekday 2 and start hour 8 are stored
in the same frozen snapshot. Normal defaults and existing seasons stay
unchanged; server receipt time, the season bounds and every other validation
still apply. See [camera and QA setup](../CAMERA_AND_QA_SEASONS.md).

## P-S10-P-S11: cooldown and retry

Exactly 120 seconds between accepted entries, per membership/lobby, across
all categories and territories. At +119 seconds block; at +120 permit normal
validation. Keep the current photo/selection and display the remaining wait.
Failed attempts do not restart it. A known capture ID recovers its saved
result instead of re-awarding base points or owner income, including after
window/season close. No scored entry is created after a failed photo upload.

## P-S12: author corrections and replay

Only the author may correct drink/size before original submission +120
seconds and before season end. The exact deadline is exclusive. A timely edit
may finish after the weekly Sunday cutoff, but never after season end. These
boundary defaults implement the previously open O-S02.

Keep original time, location, photo and order. Edits restart neither deadline
nor cooldown. Record old/new selection, actor, time and revision. Replay
corrected source entries in original event order and recalculate every affected
owner recipient/income, territory owner and leaderboard total. A different
stale revision is rejected; retrying the already applied selection recovers
its result without another audit row or awards.

## P-S13: season settings, reset and legacy preservation

Each new v1 season stores its complete rules and timezone. Its dates, lobby,
duration label, rules and timezone are frozen. Existing populated legacy
seasons cannot be converted to v1 by an update and retain original points and
scoring behaviour. Agreed changes apply to new lobbies, not old records.

Use the existing 7/30/91-day duration choices. As decided on 18 November
2026 (RULES.md R-R03), a lobby has one competition and cannot be renewed.
New competitions require new lobbies. Migration 009 serializes inserts to
reject a second season, retaining any existing multi-season history. New
lobbies start with fresh scores/ownership without deleting old history. Host-only management and calendar-month semantics
remain team review items; no host role was invented.

## P-S14-P-S15: history, access and images

History labels submission and photo receipt separately, with seconds, offset
and named season timezone. Show drink/size, base season/territory awards,
owner recipient/income and corrections. Re-fetch after updates. A photo's
receipt time is not claimed to be its physical shutter time.

Check current membership and season/lobby scope on game pages and in mutation
functions. Photo deletion/expiry preserves the source scoring event and its
income; image privacy and retention remain governed by R6/R7. Server-only
functions and revision records deny public clients. Raw GPS is discarded
after existing location evaluation and image metadata is stripped.

## Remaining dependencies

Migration 005 and shared-project/live verification remain pending. Phone
GPS (followed automatically), the 50 m accuracy limit, border handling and
the 60 s reading age are decided (R-L01–R-L04). Later confirmation
remains D-14. Minigame nights, multipliers and interruptions remain separate.
No leaving/absence or exceptional moderation workflow is introduced. The
historical three-page PDF and its original source snapshot are kept for
review traceability; this file is the current implemented contract.

## Lobby migration 007 compatibility revision

The 18 November compatibility PR preserves this contract and the current
create/join/start-season flow. Its revised migration exposes a server-only,
read-only lobby snapshot view; it introduces no owner role, player minimum,
capacity limit, invitation/removal workflow, calendar-month change or new
scoring gate. Migration 005 stays authoritative. The original recovered
lobby-battles draft is superseded; review and verification are recorded in
[the migration handoff](../LOBBY_MIGRATION_REVIEW.md).

## Team-mode extension (18 November 2026)

R-TEAM01–R-TEAM05 extend this contract for newly created team lobbies. Replace
the scoring competitor with the entry's immutable team ID. Combine members'
base points in each territory and season; pay prior-owner income only for a
rival team's entry, to the owning team. Individual seasons keep their existing
behavior. Replay, correction order, quarter points, ties and per-player
cooldown remain unchanged. See [TEAM_MODE.md](../TEAM_MODE.md) for migration
010 and verification. Team scores are the competition's sole ranked totals.
