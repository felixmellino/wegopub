# WeGoPub: Scoring and Territory Income

**Version 1.0 | 17 November 2026 | Scoring branch**

**Status: selected by the Drink Entries & Scoring contributor; awaiting team approval. Not implemented.**

This document records the scoring discussion and the user's latest choices. It is the canonical source for the accompanying PDF, not a claim that the shared database or app already follows these rules. Existing code and previously agreed rules remain the implementation baseline until the team approves a coordinated change.

The proposal covers the quick drink-entry interface, the complete point table, separate season and territory accounts, 25% ownership income, weekly eligibility, cooldowns, duplicate protection, corrections and replay, history, and the handoff to other project blocks. It carries forward the existing photo privacy rules and identifies decisions that remain open.

**Reading guide:** sections 01-09 describe the proposed experience and rules; section 10 preserves the decision trail; sections 11-13 cover implementation responsibilities, outstanding approvals and verification. Stable P-S identifiers connect the proposal to the other ontology files. Open issues use O-S identifiers.

**Review route:** Drink Entries & Scoring -> Location & Territories -> Standings & Data -> Identity & Lobbies. Teammates should explicitly confirm the rules that affect their block before code or schema changes begin.

## 01 / What the team is being asked to approve

The season competition remains individual. A player's season total determines the season ranking. Territories have separate player totals that determine ownership. In this proposal, "overall points" means the current lobby's season total; a cross-lobby or lifetime competition has not been defined.

The proposed experience is quick: take a fresh photo, choose one of four drink categories, choose a size when required, review the points preview and submit. Players do not calculate points, ownership percentages or fractional awards themselves.

The drinker receives their full base points. An existing territory owner can receive additional season income from another player's accepted entry. That income never strengthens the owner's territory total. This is an additional award, not a tax deducted from the visitor.

Three design choices are deliberate: the point scale is small, drink sizes are selected honestly in a friends' game, and ownership income and the number of scoring entries have no fixed nightly cap. A two-minute posting cooldown and duplicate protection still apply.

| Area | Selected proposal |
| --- | --- |
| Drink menu | Beer, wine, shot, mixed drink; cocktails and long drinks share the mixed category |
| Base scale | Fixed whole-number awards from 1 to 5; large-size bonuses already included |
| Owner income | Additional 25% of another player's base award; season account only |
| Precision | Exact quarter-points in season totals |
| Weekly window | Continuous Thursday 18:00 to Sunday 18:00, in the lobby timezone |
| Posting interval | Two minutes per player per lobby, across all categories |
| Corrections | Two minutes; recalculate affected ownership and subsequent bonuses |
| Season consistency | Scoring rules and timezone fixed during an active season |

Selected means chosen in this conversation for the team proposal. It does not mean that all four teammates have approved it. Recommended safeguards and unresolved boundaries are identified separately below. No application code, migrations or saved player data are changed by publishing this document.

## 02 / Drink menu, sizes and base points

<a id="p-s01"></a>
### P-S01: Four quick-select categories

Use Beer, Wine, Shot and Mixed drink. Cocktails and long drinks belong to Mixed drink. Cider and an alcohol-free scoring category were offered during discussion but were not selected for this initial menu. Their absence is a scope decision for this proposal, not a statement about future features.

<a id="p-s02"></a>
### P-S02: Size labels with practical definitions

Beer, wine and mixed drinks use Small / Medium / Large. Earlier questions used "Regular"; the consolidated proposal calls that middle choice Medium. Beer and wine show the volume beneath the label. Mixed drinks use the three labels without asking players for mixer volumes, spirit measures or a recipe calculation. Shots have one serving and no size-selection step. No exact shot volume was agreed.

| Category | Small | Medium | Large |
| --- | --- | --- | --- |
| Beer | 250 ml | 330 ml | 500 ml |
| Wine | 100 ml | 150 ml | 250 ml |
| Mixed drink | Player selects Small | Player selects Medium | Player selects Large |
| Shot | One serving; no size selector | Not applicable | Not applicable |

<a id="p-s03"></a>
### P-S03: Final proposed point table

| Category | Small | Medium | Large |
| --- | --- | --- | --- |
| Beer | 1 | 2 | 3 |
| Wine | 1 | 2 | 4 |
| Mixed drink | 2 | 3 | 5 |
| Shot | 4 for one serving | Not applicable | Not applicable |

These are the complete base awards. The selected +1 large-size bonus is embedded in each Large value; the app must not add another +1 after looking up the table. The ownership calculation uses this final base award, including its embedded size bonus.

The beer comparison is explicit: two 250 ml beers earn 1 + 1 = 2; one 500 ml beer earns 3. The Large beer therefore includes the chosen +1 advantage over two Small beers. The initial 6/8/13 discussion was illustrative and has been superseded by this table. The final values are fixed game choices, not a strict millilitre or alcohol-content formula. For example, a 330 ml beer earns 2 rather than a fractional volume-derived result.

## 03 / Two accounts and exact owner income

<a id="p-s05"></a>
### P-S05: Separate season and territory totals

For an otherwise eligible entry inside a territory, the drinker receives the base award in their season total and in their account for that territory. A verified entry outside every territory receives season points only. There is no territory owner to reward for an outside entry.

All totals, ownership and awards are scoped to the entry's lobby and season. Another lobby's players or ownership cannot affect them. The player's own base award is the same in both applicable accounts; the additional owner-income stream is what makes season and territory totals diverge.

<a id="p-s06"></a>
### P-S06: Additional 25% income, with no deductions

When another player submits an accepted territory entry, its owner receives 25% of that entry's base award as additional season points. The drinker keeps every base point. The owner receives no territory points from that income. There is no self-income when the owner logs their own drink, no fixed income cap and no requirement in this proposal to split a visitor's award.

| Base award | Drinker season award | Drinker territory award | Other owner's season income |
| --- | --- | --- | --- |
| 1 | 1 | 1 | 0.25 |
| 2 | 2 | 2 | 0.50 |
| 3 | 3 | 3 | 0.75 |
| 4 | 4 | 4 | 1.00 |
| 5 | 5 | 5 | 1.25 |

Season total = the player's accepted base awards + the player's earned owner income, using the current corrected history. A territory total contains only that player's base awards assigned to the territory. Owner income cannot claim or defend a territory.

Keep exact quarter-points. Do not round every bonus to a whole point and do not delay a fractional award until it reaches 1. The app may display 12.75, for example. The Data teammate can choose exact decimal storage or integer quarter-units; the storage design is not decided here. Display formatting must not change the amount used in rankings.

For an unclaimed territory, the proposed default is no owner income on its first entry. Initial claims and season resets still require team confirmation under O-S01.

## 04 / Ownership order, captures and ties

<a id="p-s07"></a>
### P-S07: Reward the prior owner, then change ownership

For each valid entry in a territory, identify the owner immediately before that entry in the authoritative event order. Credit the drinker's full base points. If that prior owner is a different player, credit their 25% season income. Then update territory totals and determine ownership. A capturing entry can therefore give one final bonus to the outgoing owner.

An owner's own check-in gives normal base points only. Becoming the new owner does not create a bonus on that player's capturing drink. A score preview is an estimate because another entry may change the owner before acceptance.

<a id="p-s08"></a>
### P-S08: Highest territory total; earliest arrival at a tied score

The highest territory total owns the area. When totals tie, the player who reached the tied score first ranks higher, following existing rule R-R01. The same principle applies to season rankings, including the owner-income events that contribute to them. An exact tie reached in the same event still needs a team-approved fallback, under O-S03.

The example below assumes a fresh, unclaimed territory and one lobby timezone. That starting state is an illustration of the recommended reset policy, not a separately approved reset rule. Each player's entries are two minutes apart. Totals in the middle columns are Mia / Leo.

| Time | Accepted entry | Territory totals | Season totals | Owner after |
| --- | --- | --- | --- | --- |
| Thu 18:00 | Mia: Large beer, 3 | 3 / 0 | 3 / 0 | Mia |
| Thu 18:01 | Leo: Shot, 4 | 3 / 4 | 4 / 4 | Leo |
| Thu 18:02 | Mia: Medium mixed, 3 | 6 / 4 | 7 / 4.75 | Mia |
| Thu 18:03 | Leo: Medium beer, 2 | 6 / 6 | 7.50 / 6.75 | Mia |
| Thu 18:04 | Mia: Medium wine, 2 | 8 / 6 | 9.50 / 6.75 | Mia |

Leo's Shot gives Mia 1 before Leo captures the territory. Mia's mixed drink gives Leo 0.75 before she captures it back. Leo's next beer gives Mia 0.50 but only brings his territory total level with hers, so Mia keeps ownership. Mia's final own-territory drink generates no additional self-bonus.

## 05 / Weekly eligibility and the shared clock

<a id="p-s09"></a>
### P-S09: One continuous Thursday-to-Sunday window

Scoring opens every Thursday at 18:00 inclusive and closes every Sunday at 18:00 exclusive, in the lobby's chosen shared timezone. Every intervening time is eligible: Friday afternoon, Saturday morning and after-midnight entries are not treated differently. There are no separate nightly openings inside this continuous window.

The server's submission-receipt timestamp determines weekly eligibility. The camera photo's receipt time, its metadata and the phone's clock cannot backdate a submission into the window. A photo received at Sunday 17:59 followed by a submission received at 18:01 is outside the window.

| Local lobby time | Weekly-window outcome |
| --- | --- |
| Thursday 17:59:59 | Closed |
| Thursday 18:00:00 | Open |
| Friday or Saturday, any hour | Open |
| Sunday 17:59:59 | Open |
| Sunday 18:00:00 | Closed |
| Monday, any hour | Closed |

Outside the window, block new submissions and show the next opening with its full date, time and timezone. Do not save an out-of-window history entry with zero points. That older prototype behaviour was explicitly rejected. An attempt rejected for timing changes no score and earns no owner income.

Each lobby chooses one timezone for everyone in that lobby. A player travelling with a different phone timezone still follows the lobby clock. The timezone is fixed for the active season under P-S13. Exact timezone configuration permissions and defaults remain a shared setup decision.

Technical recommendation for review: store authoritative instants consistently and derive the weekly boundaries in the named lobby timezone, including its clock changes. Do not implement this as an unconditional fixed 72-hour duration. Active-season eligibility is also required; exact season starts, ends and correction grace at those boundaries are open under O-S01 and O-S02.

This weekly scoring window does not define a minigame "night." The separate one-minigame-per-night rule still needs its own agreed night boundaries.

## 06 / Posting cooldown and duplicate protection

<a id="p-s10"></a>
### P-S10: Two minutes between accepted entries

Apply one two-minute cooldown to each player within a lobby, across every drink category and size. Switching from beer to shot, changing size or using another territory cannot bypass it. Another player has their own interval. Another lobby has a separate interval; lobby membership and account rules must still be checked there.

An entry recorded at 20:00:00 permits another at 20:02:00, subject to every other validation. A request at 20:01:59 is too early. At exactly two minutes the time restriction has expired. There is no fixed number of scoring entries per night or per weekly window.

When too early, retain the selected drink, size and fresh photo on the form, show the remaining wait and save no entry or points. There is no owner income. Failed attempts do not restart the cooldown. The latest user correction replaced the brief five-minute choice with two minutes.

<a id="p-s11"></a>
### P-S11: A retry is the same submission

Cooldowns apply to genuinely new entries. Double-clicking Submit, reconnecting or retrying after an uncertain response must retrieve the original submission's result, not create a new scored entry. Its associated owner award must also exist only once. A retry does not get a fresh scoring timestamp, a second income award or a second cooldown start.

| Situation | Required outcome |
| --- | --- |
| Upload fails | No scored entry and no owner award |
| Save reply is lost after a successful write | Recover the already accepted entry and linked award |
| Submit is pressed twice | One entry and one set of awards |
| New drink is submitted before two minutes | Keep the form; save nothing; show the remaining interval |
| New drink arrives at exactly two minutes | Permit normal validation to continue |
| Correction arrives | Apply P-S12; do not create a second drink entry |

The weekly cutoff and all other eligibility rules still apply when a player waits out the cooldown. A form being open before Sunday 18:00 does not reserve scoring eligibility after the window closes.

## 07 / Corrections and replay

<a id="p-s12"></a>
### P-S12: Two-minute corrections with consistent downstream results

The selected policy allows a player to correct a wrong drink category or size within two minutes of the original accepted entry. Update its base award and linked owner income, then recalculate ownership and all affected later owner bonuses using the corrected entry. Preserve the original place of the entry in the scoring sequence. An edit is not another drink and must not duplicate its base award.

This deliberately rejects the alternative of keeping every later bonus unchanged. A wrong Large selection could temporarily make someone an owner. If they correct it to Small, later visitors' owner income must go to the owner determined by the corrected history. The correction can consequently change other players' season totals and current territory ownership.

Replay the affected history in its authoritative original order, apply the frozen season rules and recompute dependent awards. It must not apply a percentage to a total that already includes an earlier owner bonus, or create income on income. Repeating the same correction request must not add another set of adjustments.

Recommended safeguards for team approval:

- Only the entry's author can correct the drink or size. Other players' access to lobby photos does not grant edit permission.
- Keep the original submission timestamp, verified location and territory assignment. A correction cannot move the entry to a different time or place.
- Keep an audit record of old and new selections, the correction time and resulting award changes. History should identify a corrected entry.
- The deadline runs from original acceptance; edits restart neither that deadline nor the original posting cooldown.
- Use a half-open edit window: before original time + 120 seconds is allowed; at exactly that deadline is closed. This exact boundary is a proposed default for team confirmation.
- Check the deadline when the server receives the correction, not when an edit form was opened.

Whether an otherwise timely correction is allowed after Sunday 18:00 or a season end remains open under O-S02. A new entry is always blocked outside the scoring window; the correction policy must explicitly distinguish editing an existing accepted entry from submitting a new one.

The UI should explain that other totals may change after a correction. The Data and Territory/Standings owners need to approve the replay and audit approach before implementation.

## 08 / Worked correction example

This example uses the selected point table and assumes an unclaimed starting territory. All timestamps are in one lobby timezone. The original history is:

| Time | Accepted entry | Result relevant to ownership |
| --- | --- | --- |
| 18:00:00 | Mia: Large beer, 3 | Mia owns with 3 territory points |
| 18:01:00 | Leo: Medium beer, 2 | Mia gets 0.50; Leo has 2 territory points |
| 18:03:00 | Leo: Large wine, 4 | Mia gets 1.00; Leo reaches 6 and captures |
| 18:03:15 | Eva: Shot, 4 | Leo gets 1.00; his 6 still leads Eva's 4 |
| 18:04:00 | Leo corrects that wine to Small, 1 | Edit is one minute after the original entry |

After the correction, replay from Leo's wine entry. Mia still owns immediately before it. The corrected wine gives Leo 1 rather than 4, and Mia receives 0.25 rather than 1.00. Leo reaches 3 territory points, tying Mia; Mia reached 3 first, so Leo never becomes owner in the corrected history.

Eva's later Shot must therefore reward Mia with 1.00, not Leo. Eva then reaches 4 territory points and becomes owner herself. Updating only Leo's wine award would leave the later bonus and the current owner incorrect.

| Player | Territory before | Territory after | Season before | Season after |
| --- | --- | --- | --- | --- |
| Mia | 3 | 3 | 4.50 | 4.75 |
| Leo | 6 | 3 | 7.00 | 3.00 |
| Eva | 4 | 4 | 4.00 | 4.00 |

The current owner changes from Leo to Eva. Mia's original wine-related income falls by 0.75, but she gains the 1.00 from Eva's Shot, leaving her season total 0.25 higher overall. Leo loses 3 base points and the 1.00 income he should not retain. Eva's base award is unchanged.

This is the chosen replay behaviour, not a new penalty. The correction record should make the cause understandable. The original photo and receipt history remain attached to the same entry. Replay must finish consistently before the app presents the updated rankings as final.

## 09 / Fast interface, history and photo protection

<a id="p-s04"></a>
### P-S04: Few taps and trusted selection

The proposed flow is: fresh camera photo -> drink category -> size when required -> points preview -> submit. A Shot skips the size step. Clear buttons replace free-form amount calculations. The exact visual ordering of the camera and buttons can be tested later; the player should not need to enter percentages, recipes or custom point values.

Mixed-drink sizes intentionally use honest Small / Medium / Large selection. This is a friends' game and classification will not be perfect. A photo helps the lobby review the selection; it does not establish the exact recipe, pour or hidden contents. Strict image analysis was not selected as a prerequisite.

<a id="p-s14"></a>
### P-S14: Explain every award and correction

Photo/entry history should show the username, category, size, applicable volume label, precise submission date and time including seconds, and the lobby timezone. Show the territory name or "Outside game territories," the base award to the drinker, and any owner-income amount and recipient. Corrections need their own timestamp and an understandable old/new comparison.

Photo receipt and submission are different events. If both are shown, label them separately. The existing photo timestamp records when the app received the camera image; it is not guaranteed to be the physical camera-shutter time. Eligibility uses submission receipt. Owner income should link to its source check-in so someone can explain a total such as 12.75.

<a id="p-s15"></a>
### P-S15: Keep existing photo and location protections

Carry forward the agreed fresh-camera requirement, signed-in current-lobby access, metadata removal and disposal of exact GPS after verification. Store the verification result and matched territory. A missing or uncertain location must not silently become a successful scored entry. The proposed later friend-confirmation fallback in D-14 remains separate and unapproved for this scoring implementation.

The photo owner can delete the stored photo while keeping the accepted entry and its scores. Image removal alone does not reverse the drinker's base award or its associated owner income. Access expires 30 days after the season ends; physical cleanup needs the scheduled maintenance job. Copies already saved by viewers cannot be recalled.

The photo-storage implementation was merged in PR #7. The earlier read-only live check found the capture-time column missing and the photo bucket unavailable. That is a dated setup observation, not a current claim that the Data teammate has or has not since completed migration. Recheck before live validation. No credential values, player records or private project secrets belong in this proposal or its PDF.

## 10 / Frozen rules, scope and design tradeoffs

<a id="p-s13"></a>
### P-S13: Stable rules during each season

Keep the point table, owner-income percentage, weekly scoring window, cooldown and chosen lobby timezone fixed during an active season. Agreed changes start with a subsequent season. Do not silently apply this new point table to existing historical entries or reinterpret a completed competition.

The frozen-rule choice does not prohibit the selected two-minute correction mechanism. A correction applies the same season rules to an amended drink/size selection; it does not change the rules themselves. Rule versioning and legacy migration need a coordinated plan under O-S07.

The proposal concerns drinks and territory income. Special-item multipliers, territory shields, team events and minigame interruptions are not defined by it. A future multiplier will need an explicit stacking order and a decision about whether owner income is calculated before or after that effect. Until agreed, the ownership calculation is 25% of the P-S03 base award only.

Ownership income is intentionally uncapped. For illustration, if an owner earns 12 base points and three other players each earn 12 base points in their territories while that person owns them, the owner receives 9 additional points and totals 21. The others retain their own 12. This is an illustration of the chosen 25% rule, not a promise that ownership persists throughout any real sequence.

The team should review that strategic effect consciously. No 5-point or 10-point owner-income cap was selected. No 4-entry or 6-entry nightly scoring limit was selected. The cooldown and duplicate rules still apply. These decisions can be revisited for a later season through the frozen-rules policy.

For a first claim, proposed defaults are a fresh season with unclaimed territories, followed by ownership for the first positive eligible territory score. These reset/default choices remain open to the team. Login state, physical presence requirements for passive income and membership-leaving behaviour were not separately defined and should not be invented during coding.

## 11 / Conversation decision trail

This register preserves the latest choice and the superseded alternatives. It is a record of user selections for a proposal, not evidence of full-team approval.

| Step | Latest selection and consequence | Trace |
| --- | --- | --- |
| 1 | Four categories; cocktails and long drinks grouped as Mixed | P-S01 |
| 2 | Size labels for everything except Shots | P-S02 |
| 3 | Beer 250/330/500 ml; wine 100/150/250 ml; mixed sizes selected honestly | P-S02, P-S04 |
| 4 | Large beer should equal two Small beers plus a bonus; +1 selected | P-S03 |
| 5 | Higher illustrative values replaced by the final 1-5 table | P-S03 |
| 6 | Extend the embedded +1 Large bonus to beer, wine and mixed drinks | P-S03 |
| 7 | Owner receives an additional 25%; visitor keeps full points | P-S05, P-S06 |
| 8 | Owner income goes to season only; keep exact quarter-points | P-S06 |
| 9 | Use the prior owner on a capture; no extra income on own entries | P-S07 |
| 10 | Uncapped ownership income; no fixed nightly count of scoring entries | P-S06, P-S10 |
| 11 | Continuous Thu 18:00-Sun 18:00; each lobby chooses a shared timezone | P-S09 |
| 12 | Submission receipt controls eligibility; block outside-window entries | P-S09 |
| 13 | Five-minute choice explicitly corrected to TWO minutes; keep rejected form | P-S10 |
| 14 | Rules and timezone fixed for the active season | P-S13 |
| 15 | Permit drink/size corrections for two minutes | P-S12 |
| 16 | Replay affected ownership and all later owner bonuses after a correction | P-S12 |

Earlier alternatives are not active requirements: 6/8/10 beer points, the illustrative 6/8/13 scale, nightly-only or whole-day windows, mandatory Lisbon time for every lobby, visitor deductions, whole-point bonus rounding, self-bonuses, fixed nightly caps and a five-minute cooldown. The definitive value is in the linked P-S rule, not in an older question option.

The current implementation still contains older placeholders and behaviours. Its beer/wine amount input, flat Shot/long-drink awards, older time window and same-category duplicate guard are not proof that this proposal is already supported. They must be reviewed and replaced only after team agreement.

## 12 / Team handoff and data requirements

| Project block | Review and implementation responsibility |
| --- | --- |
| Drink Entries & Scoring | Category/size lookup, base awards, eligibility integration, cooldowns, correction policy and acceptance cases |
| Location & Territories | Verified assignment, boundary handling, ownership calculations and replay order with the scoring block |
| Standings & Data | Separate award recipients/accounts, exact quarters, linked owner income, idempotent persistence, replay and ranking consistency |
| Identity & Lobbies | Current membership checks, lobby timezone configuration and season setup with the Data owner |

The Data design must distinguish a drinker's base award from another player's owner-income award. A single total on the drinker's entry cannot by itself describe both recipients and both score accounts. The proposal requires traceability to the source check-in, recipient, lobby/season, applicable frozen rules and ordering information. A linked award record or equivalent derived view is a possible implementation, not an approved schema in this document.

For corrections, retain sufficient original/revision information to reconstruct a consistent history. A corrected selection must not destroy the explanation for an earlier display or create duplicate income on replay. Store exact awards and compute both the map and leaderboard from the same accepted interpretation.

Agree one authoritative event order and make acceptance safe when two players act concurrently. Eligibility timestamps must be server-generated; deterministic ordering may need more precision or a sequence than the seconds shown in history. Updating the entry, linked awards and ownership interpretation must not expose partially recalculated rankings as a completed result.

Existing same-points fields and integer-only totals need review. The repository's current owner-modifier hook is a no-op and is not sufficient for this additional income design. The per-lobby timezone and frozen rule settings are proposed shared-model changes requiring teammate approval. This handoff does not authorize direct edits or resets of the team's shared database.

After approval, update decided ontology rules, implement small reviewable changes, run accepted/rejected/boundary tests and verify persisted results after restart. Use the Scoring branch, a pull request and teammate review. Keep server credentials outside Git and the shared PDF. Photo-storage setup and its live validation remain a separate prerequisite for the complete check-in demonstration.

## 13 / Outstanding approvals and acceptance checklist

The following are explicitly open. Suggested defaults are recommendations, not additional user-approved choices.

| Open ID | Decision still required | Suggested starting point / owner |
| --- | --- | --- |
| O-S01 | Season start/end, reset and initial territory ownership | Fresh scores and unclaimed territories; Data + Lobby + Territory owners confirm |
| O-S02 | Correction at exactly 120 seconds; after Sunday close; at season end | Close at exactly 120 seconds; agree any closing grace before coding; Scoring + Data |
| O-S03 | Concurrent event order and a genuinely same-event tie | Deterministic ordering; consider prior ranking as fallback; Data + Standings + Territories |
| O-S04 | Timezone setup permissions, validation and default | One named zone per lobby, fixed in season; Identity/Lobbies + Data |
| O-S05 | GPS source, age, accuracy and shared-border acceptance | Location owner resolves D-09/D-10; D-14 fallback remains separate |
| O-S06 | Minigame nights, special items and multiplier interaction | Separate from the continuous drink window; minigame owner + team |
| O-S07 | Activation and legacy season migration | Activate approved rules for a new season; preserve historical rules and results; Data + team |

The exact shot volume, how an absent/removed owner is treated, and any exceptional post-deadline moderation are also unspecified. Keep these visible as follow-up scope rather than quietly inventing mechanics. They need resolution before implementing behaviour that depends on them; they need not expand the initial interface into recipe or volume entry.

These are future acceptance requirements, not a report that the current app passes the new scoring rules:

| Case | Expected result under the selected proposal |
| --- | --- |
| Every supported category/size | Exact P-S03 award; no double-added Large bonus |
| Valid matched visitor entry | Full base to visitor; 25% to prior owner season only |
| Own-territory entry | Base only; no self-income |
| Verified outside entry | Base season points only; no territory or owner award |
| Missing/uncertain GPS or invalid input | No successful scored entry |
| Capturing entry | Prior owner gets income; ownership changes afterwards |
| Territory tie | Earliest arrival at the tied score keeps precedence |
| Thursday 18:00 / Sunday 18:00 | First is open; second is closed in lobby timezone |
| Photo before closing, submission after | Submission blocked; photo time does not backdate it |
| Other phone timezone | Lobby clock still determines eligibility |
| New entry at +119 / +120 seconds | First rejected; second can continue through validation |
| Another category during cooldown | Same cooldown; keep form and change no scores |
| Failed upload or failed validation | No award; no cooldown restart |
| Lost response / duplicate retry | Recover one accepted entry and one set of awards |
| Timely size/type correction | Recalculate own award, linked income and affected downstream history |
| Same correction retried | Same resulting history; no duplicate adjustments |
| Unauthorised correction attempt | Reject before changing any entry, award or audit data |
| Photo deletion or expiry | Image unavailable; entry and scoring history retained |
| Restart after accepted entry/correction | Same source data, totals, ownership and history explanation |

Before writing implementation code, obtain explicit teammate confirmation of the selected rules, mark remaining boundaries and assign owners. Then record the agreed changes in RULES.md and the shared data contract. This document and its PDF remain the traceable review baseline until superseded by an approved version.
