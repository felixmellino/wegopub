# Rules

## Direction agreed on 17 November 2026

The user's updated direction replaces buddy confirmation. Exact values and
boundary behavior listed in `OPEN_DECISIONS.md` are not yet agreed.

| ID | Rule | Allowed / rejected / boundary outcomes |
| --- | --- | --- |
| R1 | A city is divided into territories; an accepted check-in contributes to its territory. | Map a valid coordinate to a territory. Missing, inaccurate, outside-city or boundary coordinates require the decisions below; never silently assign a territory. |
| R2 | Check-in requires drink type, drink size, a photo and automatic location verification; no buddy action. | Award points only after validation. Missing required inputs or failed verification do not award points. Photo metadata alone is not proof of presence or drink contents. |
| R3 | Base points depend on both drink type and size; beer earns fewer points than a longdrink in the intended comparison. | Accept only configured type/size combinations. Reject unsupported combinations. Exact table, units and comparisons between different sizes remain open. |
| R4 | The player with the most points in a territory owns it. | A unique leader owns the territory. Ties, initial ownership, scoring window and resets remain open. |
| R5 | Other players earn a percentage fewer points on a drink in an owned territory than its owner. | Apply the agreed reduction to non-owners. Percentage, rounding, unclaimed territory behavior and ownership timing remain open. |

## Implementation recommendations (not yet agreed rules)

- Capture current device location alongside a newly captured photo. Inspect
  embedded photo coordinates when available as supplementary evidence.
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
