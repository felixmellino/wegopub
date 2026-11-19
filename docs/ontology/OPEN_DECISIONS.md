# Open Decisions

Quiz Duel decisions (19 November 2026) are recorded in [QUIZ_DUEL.md](QUIZ_DUEL.md).
The feature branch implements invitations, reserved stakes, timed rounds and team
purses. PR #60 is merged and shared-project migration 016 was applied on
19 November 2026. Installation/status checks passed; full deployed two-player
gameplay remains to verify. See the [handoff](../QUIZ_DUEL.md).

This file tracks team review and unresolved decisions. [SCORING_V1.md](SCORING_V1.md) records the working implementation authorised by the contributor; teammate review, merge, migration and live verification remain pending. The [planning record](SCORING_PROPOSAL.md) preserves earlier choices.

The current check-in rules use automatic location verification. D-14 proposes a fallback for cases where that check fails.

| ID | Topic | Open question |
| --- | --- | --- |
| D-01 | Owner advantage | Implemented on Scoring: additional 25% prior-owner income, season only, exact quarters, no visitor deduction/self-income/cap. Team review and migration pending. See [v1](SCORING_V1.md). |
| D-02 | Points per Drink | Implemented on Scoring: four categories and frozen fixed size table; Large bonuses embedded. Legacy seasons preserved. Team review pending. See [v1](SCORING_V1.md). |
| D-03 | Territory areas | **Decided 2026-11-17**, see [R-T01 and R-T02](RULES.md#territories). Nova SBE campus added 2026-11-18. Still open: possibly Praça das Flores. |
| D-04 | Special items | Chug Duel explicitly uses a base-season-point transfer instead of items (R-M03, contributor decision 18 November 2026). Items/effects for other games remain open. |
| D-05 | Game Night boundaries | Implemented on Scoring: continuous Thu 18:00 inclusive-Sun 18:00 exclusive in the season timezone; database scoring-request receipt is authoritative. Outside submissions blocked. Minigame nights remain separate. See [v1](SCORING_V1.md). |
| D-06 | Season follow-ups | The three length choices are decided in [R-R02](RULES.md#r-r02-season-length); that decision is closed. Scoring retains their existing 7/30/91 elapsed-day implementation. Remaining review: calendar-month semantics and host roles. Decided 18 November 2026 in R-R03: one competition per lobby, no renewal; a new competition requires a new lobby. Existing history is retained. See [v1](SCORING_V1.md). |
| D-07 | Minigame interruption | **Decided for Chug Duel**, R-M02/R-M05: reserve on acceptance; consume on start; resume after disconnect; a started abort retains both normal drink awards and consumes the used roles. Other games remain open. |
| D-08 | Ownership timing | Implemented on Scoring: prior owner paid before captures; serialized database event order; corrections replay affected history. Exact same-event tie default is recorded in D-17. See [v1](SCORING_V1.md). |
| D-09 | Location source | **Decided 2026-11-17**, see [R-L01](RULES.md#location): phone GPS at submission only, photo GPS is not used. |
| D-10 | Location acceptance | **Decided 2026-11-17/18**, see [R-L02, R-L03, R-L04](RULES.md#location): at most 50 m inaccuracy, the measured point decides at borders, readings at most 60 s old. |
| D-11 | Photo validation | Trust-based category/size selection, with lobby photo review, is selected for the proposal; exact shot volume and stronger reuse detection remain unspecified. See [P-S02/P-S04](SCORING_PROPOSAL.md#p-s04). |
| D-12 | Check-in limits | Implemented on Scoring: TWO-minute shared per-member/lobby cooldown; retain rejected form; retries award once; no fixed nightly count. See [v1](SCORING_V1.md). |
| D-13 | Privacy | **Photo lifecycle decided 2026-11-17**, see R7: owner deletion preserves the score; photos expire 30 days after the season ends. **Sharing decided 2026-11-19**, R6/R-PH01: account-wide opt-in, OFF by default, retroactive, internal team access and unanimous current-team consent for opponents; independent Chug Duel copies. The [photo workflow](WORKFLOWS.md#save-and-view-a-check-in-photo) defines stored data and access. Migration 013 was applied to shared Supabase on 19 November 2026; all eight schema/access/data checks and a fresh app-server read passed. Deployed UI verification remains pending. Still needed before real use: privacy contact, published notice, provider region and backup/deletion procedures, and scheduled cleanup. |
| D-14 | Later confirmation by another player | Should R2 allow the [proposed confirmation fallback](WORKFLOWS.md#proposed-fallback-after-automatic-location-verification-fails) when automatic location verification fails? |
| D-15 | Entry corrections | Implemented on Scoring: author can correct drink/size before original submission +120s and season end. Timely edits may finish after weekly closing. Audit and downstream replay included; defaults await team review. See [v1](SCORING_V1.md). |
| D-16 | Frozen scoring rules and timezone | Implemented on Scoring: v1 season dates, lobby, rules, version and timezone immutable. New rules start in later seasons; populated legacy seasons cannot be upgraded in place. See [v1](SCORING_V1.md). |
| D-17 | Exact ties and concurrent ordering | Working default: database acceptance order resolves concurrent entries. Within one event, a season-score tie preserves the previously higher-ranked owner recipient. All other ties use earliest reaching order. Team review pending. See [v1](SCORING_V1.md). |
| D-18 | Minigame selection and unlocks | **Chug Duel implemented and merged**, R-M01–R-M05. Migration 011 applied to shared Supabase with contributor authorization on 18 November 2026; live schema/RPC and read-backed page checks passed. Real two-phone gameplay remains to verify; see [handoff](../CHUG_DUEL.md). Delayed reaction and other games from the [earlier proposal](MINIGAMES_PROPOSAL.md) remain future ideas, with unlocks/targets undecided. |
| D-19 | Nightly allowance scope and duels | **Decided for Chug Duel**, contributor 18 November 2026: normal seasons allow one outgoing plus one incoming per membership/lobby/night; reset 06:00 season timezone. Explicit QA seasons allow unlimited sequential replays under R-M02; migration 012 applied to shared Supabase and live checks passed. Atomic reservations/start, active-game restrictions, ten-minute phase expiry, shared photo/location and host split screen remain. See [handoff](../CHUG_DUEL.md). The old weekly helper is unused by Chug Duel. |
| D-20 | Focus Challenge | **Approved and implemented, 19 November 2026:** teammate approval reported by contributor. R-M06–R-M09 define normal unlocks, separate attempts, fresh variation, harder tasks, resume/deadlines, x1.5 boosts, owner income and team scope. Contributor subsequently approved immediate, unlimited sequential QA play without uploads, including existing test seasons. Apply migrations 014 then 015; normal older snapshots remain disabled. Shared-project activation and human phone difficulty calibration must be verified. See [handoff](../FOCUS_CHALLENGE.md). |

Focus Challenge variation requirement, contributor 19 November 2026:
each new attempt uses unpredictable reaction delays, a fresh memory sequence
and new precision layouts under the same difficulty constraints. Resuming
an existing attempt preserves its content and running deadlines. See D-20's
[design draft](FOCUS_CHALLENGE_PROPOSAL.md#fresh-variation-on-every-new-attempt).

Design consideration: an ownership reduction can make leaders harder to
catch. Test the agreed percentage with sample standings before fixing it.

Storage integration follow-up, 18 November 2026 (D-13): live synthetic-fixture
checks passed for lobby access, revocation, owner deletion preserving scores,
30-day expiry and scoped cleanup with SDK 2.34.1. The user selected daily
GitHub Actions cleanup; the workflow is prepared but repository secrets and
hosted execution remain pending. See [verification](../STORAGE_SDK_VERIFICATION.md).
The privacy contact, notice, provider region and backup decisions remain open.

Team lobbies decided by the contributor on 18 November 2026: see
R-TEAM01–R-TEAM05. Team season/territory totals, configurable count/capacity,
random/manual joining and member-only names/pictures are implemented on the
team-mode branch. The contributor authorised applying 009 and 010 to the
shared Supabase project on 18 November 2026; all 12 post-application checks
passed. Teammate code review and deployed app verification remain pending. This does not resolve minigame items or team-event effects.

Lobby departure decided by the contributor, 19 November 2026: R-LB01–R-LB03.
Retain earned points and lifetime statistics, pause personal owner income while
absent, allow return with original history/limits/team, retain team slots, and
block departure during accepted/running duels or running Focus attempts. Local
migration/test verification accompanies migration 016. The contributor
authorized shared application on 19 November 2026: migration 016 succeeded,
all 19 live schema/access/history checks passed, and a fresh app process read
the new fields and verified nonmember RPC denial. Frontend review, merge,
deployment and deployed UI checks remain pending.

Time Duel decided by the contributor, 19 November 2026: see [R-M10](RULES.md#r-m10-time-duel)
and [the detailed rules](TIME_DUEL.md). Separate nightly duel roles, three rounds,
exact millisecond ties and automatic one-hour x1.25 season-only boosts are agreed.
Shared migration 017 was applied and verified on 19 November 2026. Teammate
review, deployment and verification on two physical phones remain pending.
