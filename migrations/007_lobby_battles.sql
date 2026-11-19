-- Compatibility-only replacement for the recovered, UNAPPLIED lobby draft.
-- Run after schema/account setup and 005_scoring_v1.sql. No game rules change.
-- Current create/join/start-season functions remain the only write paths.
-- If the old draft was applied elsewhere, stop: a table named lobby_states
-- cannot be replaced by this view. Review that database separately.
begin;

-- Derive snapshots from canonical rows, so existing and newly created
-- lobbies, memberships and frozen scoring seasons cannot drift out of sync.
-- No duplicated state, owner/capacity defaults, or client-supplied season JSON.
create or replace view public.lobby_states with (security_invoker = true) as
select l.id as lobby_id,
       jsonb_build_object(
         'id', l.id, 'name', l.name, 'invite_code', l.invite_code,
         'members', coalesce((
           select jsonb_agg(jsonb_build_object(
             'id', m.id, 'player_id', m.player_id, 'joined_at', m.joined_at
           ) order by m.joined_at, m.id)
           from public.lobby_memberships m where m.lobby_id = l.id
         ), '[]'::jsonb),
         'seasons', coalesce((
           select jsonb_agg(to_jsonb(s) order by s.starts_at, s.id)
           from public.seasons s where s.lobby_id = l.id
         ), '[]'::jsonb)
       ) as state
from public.lobbies l;

-- Includes private invite codes: only the authenticated app server may read.
-- Even the server cannot write through this view. Underlying tables retain
-- their existing server-only grants and row-level security.
revoke all on public.lobby_states from public, anon, authenticated, service_role;
grant select on public.lobby_states to service_role;

-- Deliberately no guard_battle_entry trigger or save_lobby_state RPC.
-- Migration 005 already owns weekly windows, cooldowns, corrections, frozen
-- season creation, duplicate protection and exact-quarter owner-income replay.
notify pgrst, 'reload schema';
commit;
