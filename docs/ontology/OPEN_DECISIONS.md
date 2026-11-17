# Open Decisions

The updated direction removes buddy confirmation. Resolve the following
before implementing dependent behavior:

| Topic | Decision needed |
| --- | --- |
| Drink scoring | Supported drinks and sizes (with units), exact base points, and whether size uses a lookup table or formula. |
| Owner advantage | Non-owner reduction percentage, rounding, and points in an unclaimed territory. |
| Ownership timing | Recommend ownership immediately before acceptance; define concurrent check-in ordering. |
| Ownership calculation | Do awarded points drive territory ownership as well as Season rank? Do minigame points affect territory totals? |
| Ties and resets | Tied leaders, initial ownership, scoring window and Season resets. |
| Location source | Recommend fresh phone location alongside photo capture; define photo metadata's role, missing metadata and conflicting coordinates. |
| Location acceptance | Maximum coordinate age and uncertainty, territory edge handling, outside-city submissions, and whether a nearby registered bar is required. |
| Photo validation | Fresh capture versus gallery uploads, reused photos, supported formats/size, and how to handle false drink/size declarations. |
| Check-in limits | Repeat drinks/visits, cooldowns and duplicate submissions. |
| Game nights | Exact Thursday–Sunday hours, timezone, after-midnight attribution and out-of-hours behavior. |
| Privacy | Photo visibility, coordinate retention, image metadata removal before sharing, and deletion behavior. |
| Minigames | Shared nightly limit remains; scoring and interrupted attempts still need decisions. |

Design consideration: an ownership reduction can make leaders harder to
catch. Test the agreed percentage with sample standings before fixing it.
