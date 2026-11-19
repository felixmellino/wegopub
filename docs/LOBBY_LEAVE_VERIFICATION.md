# Lobby departure: shared migration verification

Migration `016_leave_lobby.sql` was applied on 19 November 2026 through the
existing authenticated Safari Supabase SQL Editor, with explicit contributor
authorization. The dashboard project was matched to the app's configured
Supabase host before execution. Prerequisites 015, Focus expiry and persisted
lobby choices were present. Supabase reported “Success. No rows returned”.

The post-application query ran **19 checks**, all passing:

- Departure column, immutable entry absence snapshot and snapshot trigger exist.
- Active membership view and leave/rejoin functions exist.
- Anonymous/authenticated roles cannot call the leave/rejoin functions or read
  the active roster; the server role can call both functions.
- Scoring requires active membership, and replay handles absent owners.
- All pre-existing memberships remain active; historical absence snapshots are empty.
- Before/after canonical hashes of all original membership and drink-entry fields
  match. The migration preserved 25 memberships, 20 drinks, 45 base/boosted drink
  points and 26 owner-income quarters. No real player was made to leave.

A fresh Python app process subsequently connected using the existing server
configuration, read and parsed the new membership/entry fields, loaded both
current and historical memberships, and called both RPCs with nonexistent
all-zero identities. Both correctly rejected the request with PermissionError,
without changing real data. The sandbox initially blocked DNS; the same bounded
check passed with approved network access.

Local validation from implementation: `python -m pytest -q` passed 669 tests.
`python scripts/verify_leave_lobby.py` passed on disposable PostgreSQL, including
leave/rejoin, owner-income/correction parity, game interruption and expiry,
reserved team slots, concurrent check-in/departure, and database restart.

The frontend changes remain on the working branch. Teammate review, merge,
deployment and a public-app leave/rejoin walkthrough are still required.
