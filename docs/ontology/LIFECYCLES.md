# Lifecycles

> Scoring v1 implementation was authorised on 17 November 2026. See
> [the current contract](SCORING_V1.md) and [Data handoff](../SCORING_IMPLEMENTATION.md).
> Earlier scoring drafts below are historical where they differ. Legacy seasons
> retain their old behaviour; migration and teammate review are pending.


This file will hold the states each entity can be in and the transitions between them, such as a Check-in going from pending to confirmed.

## Proposed check-in and revision lifecycle

Status: contributor-selected proposal, awaiting team approval; these are conceptual states, not new database enums. See [P-S09-P-S12](SCORING_PROPOSAL.md#p-s09).

1. A draft holds the photo and selection. Rejected timing/cooldown/verification attempts create no scored entry; recoverable attempts retain the form.
2. Acceptance produces one source entry and its applicable awards. A network retry returns that same result.
3. An authorised timely correction revises the same entry and replays the affected ownership and bonus history. The original deadline and cooldown do not restart.
4. The edit window eventually closes; the exact closure/season-boundary rules still need approval.
5. Photo deletion or expiry changes image availability without removing the scoring event, as defined by R7 and [P-S15](SCORING_PROPOSAL.md#p-s15).
