# Lobby migration 007: compatibility-only revision

The original SQL was recovered from GitHub Desktop's `Lobbiecreation` stash
(`abb1979`) and published in PR #17 for review. It has **not** been applied to
the shared Supabase project: the read-only check on 18 November confirmed
that `lobby_states` was absent. The contributor authorised a compatibility PR
on 18 November and explicitly chose to preserve the current lobby flow.

## Scope

The revised `007_lobby_battles.sql` creates a server-only, read-only
`lobby_states` **view** over `lobbies`, `lobby_memberships` and `seasons`.
Snapshots always reflect the canonical records, including new lobbies and
joins made by the existing app. Seasons include their original IDs, dates,
timezones, scoring versions and frozen rules. No duplicate writable JSON
aggregate or missing application module is needed to keep this view current.
The historical filename is retained; it does not activate the old owner-
managed lobby feature.

The unsafe original `save_lobby_state` RPC and `guard_battle_entry` trigger
are omitted. Migration 005's existing functions remain authoritative for
season creation, scoring windows, duplicate handling, cooldowns, corrections,
frozen rules, tie/ownership replay and exact-quarter owner income. No
`is_active` column, ten-player limit, automatic owner assignment, new waiting
room, invitation flow or membership-removal behavior is introduced.

Historical 007 behavior: the app created/joined lobbies and allowed renewal.
**Superseded 18 November 2026 by R-R03 and migration 009:** each new lobby now
has one competition and cannot be renewed; existing history is retained. The
7/30/91 elapsed-day durations and the season's frozen timezone remain.
Check-ins use Thursday 18:00 inclusive to Sunday 18:00 exclusive in that
season's timezone. Legacy scoring records stay legacy. Host roles and
calendar-month semantics remain open team decisions, not migration defaults.

## Review and application

1. Review this PR and the disposable PostgreSQL checks below before merging.
2. The Data owner confirms schema/account setup and scoring migration 005
   exist, backs up the database, then applies **the revised file from merged
   main**. Do not use the recovered file from the old PR #17 commit.
3. If the old draft was applied in another environment, stop. Creating this
   view over an existing `lobby_states` table fails without dropping or
   rewriting that table. That environment needs its own reviewed migration.
4. Repeat execution is safe when the compatible view already exists. No
   reseeding or scoring writes occur. Friends 006 and profile pictures 008
   remain separate migrations and do not need to be rerun for this change.

The full owner-managed lobby feature remains deferred. Its source stash and
old timezone follow-up are retained locally. They must not be restored or
applied wholesale over scoring v1.

## Verification

Runtime dependencies are unchanged. Optional isolated SQL test tools:

```bash
python3 -m venv /tmp/wegopub-lobby-test
/tmp/wegopub-lobby-test/bin/python -m pip install -r requirements.txt
/tmp/wegopub-lobby-test/bin/python -m pip install pgserver==0.1.4 'psycopg[binary]==3.2.13' fasteners==0.20
/tmp/wegopub-lobby-test/bin/python scripts/verify_lobby_scoring_compat.py
/tmp/wegopub-lobby-test/bin/python -m pytest -q
```

The SQL script creates and destroys its own local PostgreSQL cluster, uses
synthetic fixtures, and never reads Supabase secrets or connects to an
existing database. In the disposable copy only, migration 005's server receipt
clock is fixed to exercise real weekly boundaries without waiting for Thursday.
Production migration 005 is unchanged.

Checks cover populated legacy/v1 preservation; ordinary create/join/start
writes; new/renamed lobby snapshots; member versus nonmember starts; 7/30/91
days; frozen rules/timezones; Python/SQL weekly boundaries in Lisbon and New
York; accepted check-ins; idempotent duplicate retries; rejection of cooldowns,
outsiders and closed windows; correction audit/conflicts; owner income; server-only read access;
repeat migration execution; real server restart; and refusal to overwrite an
old draft table. The regular Streamlit form tests retain the existing lobby
flow. Shared-project application and live verification wait for review.
