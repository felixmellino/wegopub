-- Apply after 016. Deleting a lobby hides it for everyone; nothing is erased,
-- so scores and history stay in the database (same rule as leaving a lobby).
-- Only the person who created the lobby (its earliest membership) may delete it.
begin;
alter table public.lobbies add column if not exists deleted_at timestamptz;

-- A deleted lobby has no active members: every scoring/minigame RPC that checks
-- active_lobby_memberships (_require_active_lobby etc.) now refuses it too.
create or replace view public.active_lobby_memberships with (security_invoker=true) as
 select m.* from public.lobby_memberships m
  where m.left_at is null
    and not exists (select 1 from public.lobbies l where l.id = m.lobby_id and l.deleted_at is not null)
 with local check option;

create or replace function public.delete_lobby(actor_player uuid, target_lobby uuid)
returns void language plpgsql set search_path=public as $$
declare creator uuid; lobby_row public.lobbies%rowtype; at_time timestamptz:=statement_timestamp();
begin
 perform pg_advisory_xact_lock(hashtext(target_lobby::text));
 select * into lobby_row from public.lobbies where id = target_lobby;
 if not found then raise exception 'permission_denied'; end if;
 select player_id into creator from public.lobby_memberships
  where lobby_id = target_lobby order by joined_at, id limit 1;
 if creator is distinct from actor_player then raise exception 'permission_denied'; end if;
 if lobby_row.deleted_at is not null then return; end if; -- safe retry after a lost response
 update public.chug_duels d set status='cancelled', finished_at=at_time
  from public.seasons s where s.id = d.season_id and s.lobby_id = target_lobby
   and d.status in ('invited','accepted','started');
 update public.lobbies set deleted_at = at_time where id = target_lobby;
 delete from public.player_lobby_choices where lobby_id = target_lobby;
end $$;

revoke all on function public.delete_lobby(uuid,uuid) from public,anon,authenticated;
grant execute on function public.delete_lobby(uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
