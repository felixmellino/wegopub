-- Apply after 011. Unlimited repeat plays only in frozen QA/test seasons.
begin;
alter table public.chug_duels add column if not exists test_mode boolean not null default false;
update public.chug_duels d set test_mode = coalesce(s.scoring_rules->'test_mode' = 'true'::jsonb,false)
  from public.seasons s where s.id=d.season_id
  and d.test_mode is distinct from coalesce(s.scoring_rules->'test_mode' = 'true'::jsonb,false);

-- The server derives the flag; callers cannot opt normal games out of limits.
create or replace function public._snapshot_chug_test_mode()
returns trigger language plpgsql set search_path=public as $$
begin
  if tg_op='UPDATE' and row(new.season_id,new.challenger_id,new.opponent_id,new.game_night)
      is distinct from row(old.season_id,old.challenger_id,old.opponent_id,old.game_night) then
    raise exception 'duel_identity_frozen';
  end if;
  select coalesce(s.scoring_rules->'test_mode' = 'true'::jsonb,false) into new.test_mode
    from public.seasons s where s.id=new.season_id;
  if not found then raise exception 'permission_denied'; end if;
  return new;
end $$;
drop trigger if exists snapshot_chug_test_mode on public.chug_duels;
create trigger snapshot_chug_test_mode before insert or update on public.chug_duels
  for each row execute function public._snapshot_chug_test_mode();

drop index if exists public.chug_outgoing_night;
drop index if exists public.chug_incoming_night;
create unique index chug_outgoing_night on public.chug_duels(challenger_id,game_night)
  where status in ('accepted','started','completed','aborted') and not test_mode;
create unique index chug_incoming_night on public.chug_duels(opponent_id,game_night)
  where status in ('accepted','started','completed','aborted') and not test_mode;

create or replace function public._check_chug_slots(cid uuid,oid uuid,night date,except_duel uuid)
returns void language plpgsql set search_path=public as $$
declare is_test boolean;
begin
  select d.test_mode into is_test from public.chug_duels d where d.id=except_duel;
  if not found then
    -- A new invitation has no row yet. Each lobby has one competition (R-R03).
    -- Imported older competitions are historical; the latest is authoritative.
    select coalesce(s.scoring_rules->'test_mode' = 'true'::jsonb,false) into is_test
      from public.seasons s join public.lobby_memberships m on m.lobby_id=s.lobby_id
      where m.id=cid order by s.starts_at desc,s.id limit 1;
  end if;
  if not coalesce(is_test,false) and exists(select 1 from public.chug_duels
    where id<>except_duel and game_night=night and not test_mode
    and status in ('accepted','started','completed','aborted')
    and (challenger_id=cid or opponent_id=oid)) then
    raise exception 'duel_limit';
  end if;
  -- Unlimited replays are sequential, never overlapping games for one player.
  if exists(select 1 from public.chug_duels where id<>except_duel and status in ('accepted','started')
    and (challenger_id in (cid,oid) or opponent_id in (cid,oid))) then
    raise exception 'duel_busy';
  end if;
end $$;

revoke all on function public._snapshot_chug_test_mode(),public._check_chug_slots(uuid,uuid,date,uuid)
  from public,anon,authenticated;
grant execute on function public._check_chug_slots(uuid,uuid,date,uuid) to service_role;
notify pgrst,'reload schema';
commit;
