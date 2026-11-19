-- Chug Duel: apply after 010. No existing season snapshot or entry is rewritten.
begin;
create table if not exists public.chug_duels (
  id uuid primary key,
  season_id uuid not null references public.seasons(id),
  challenger_id uuid not null references public.lobby_memberships(id),
  opponent_id uuid not null references public.lobby_memberships(id),
  game_night date not null,
  drink_type text not null,
  size text,
  status text not null default 'invited' check (status in
    ('invited','accepted','started','completed','aborted','declined','cancelled','expired')),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  accepted_at timestamptz,
  started_at timestamptz,
  play_at timestamptz,
  finished_at timestamptz,
  winner_id uuid references public.lobby_memberships(id),
  challenger_entry_id uuid not null unique default gen_random_uuid(),
  opponent_entry_id uuid not null unique default gen_random_uuid(),
  check (challenger_id <> opponent_id),
  check (challenger_entry_id <> opponent_entry_id),
  check (winner_id is null or winner_id in (challenger_id,opponent_id)),
  check (status <> 'completed' or (winner_id is not null and play_at is not null))
);
create unique index if not exists chug_outgoing_night on public.chug_duels(challenger_id,game_night)
  where status in ('accepted','started','completed','aborted');
create unique index if not exists chug_incoming_night on public.chug_duels(opponent_id,game_night)
  where status in ('accepted','started','completed','aborted');
create unique index if not exists chug_pending_invitation on public.chug_duels(challenger_id)
  where status = 'invited';
create index if not exists chug_season on public.chug_duels(season_id,created_at);
alter table public.chug_duels enable row level security;
revoke all on public.chug_duels from public,anon,authenticated;
grant all on public.chug_duels to service_role;

alter table public.drink_entries add column if not exists duel_id uuid references public.chug_duels(id);
alter table public.drink_entries add column if not exists duel_transfer_to uuid;
alter table public.drink_entries add column if not exists duel_transfer_order bigint;
create unique index if not exists chug_entry_member on public.drink_entries(duel_id,membership_id) where duel_id is not null;

create or replace function public._chug_night(at_time timestamptz,zone_name text)
returns date language sql stable set search_path = public as $$
  select (timezone(zone_name,at_time) - interval '6 hours')::date;
$$;

create or replace function public._expire_chug_duels(lid uuid,at_time timestamptz)
returns void language plpgsql set search_path = public as $$
begin
  update public.chug_duels d set status = case d.status
      when 'started' then 'aborted' when 'accepted' then 'cancelled' else 'expired' end,
    finished_at = at_time
    from public.seasons s where s.id=d.season_id and s.lobby_id=lid
      and d.status in ('invited','accepted','started')
      and (at_time >= d.expires_at or at_time >= s.ends_at
        or d.game_night <> public._chug_night(at_time,s.timezone_name)
        or not public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules));
end $$;

create or replace function public._check_chug_pair(cid uuid,oid uuid,lid uuid)
returns void language plpgsql set search_path = public as $$
declare c public.lobby_memberships%rowtype; o public.lobby_memberships%rowtype; mode text;
begin
  select * into c from public.lobby_memberships where id=cid and lobby_id=lid;
  if not found then raise exception 'permission_denied'; end if;
  select * into o from public.lobby_memberships where id=oid and lobby_id=lid;
  if not found or c.player_id=o.player_id then raise exception 'permission_denied'; end if;
  select game_mode into mode from public.lobbies where id=lid;
  if mode='team' and (c.team_id is null or o.team_id is null or c.team_id=o.team_id) then
    raise exception 'duel_team';
  end if;
end $$;

create or replace function public._check_chug_slots(cid uuid,oid uuid,night date,except_duel uuid)
returns void language plpgsql set search_path = public as $$
begin
  if exists(select 1 from public.chug_duels where id<>except_duel and game_night=night
    and status in ('accepted','started','completed','aborted') and (challenger_id=cid or opponent_id=oid)) then
    raise exception 'duel_limit';
  end if;
  if exists(select 1 from public.chug_duels where id<>except_duel and status in ('accepted','started')
    and (challenger_id in (cid,oid) or opponent_id in (cid,oid))) then raise exception 'duel_busy'; end if;
end $$;

create or replace function public.list_chug_duels(actor_player uuid,target_season uuid)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare lid uuid; mid uuid;
begin
  select s.lobby_id,m.id into lid,mid from public.seasons s join public.lobby_memberships m on m.lobby_id=s.lobby_id
    where s.id=target_season and m.player_id=actor_player;
  if not found then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  perform public._expire_chug_duels(lid,statement_timestamp());
  return query select * from public.chug_duels where season_id=target_season
    and (challenger_id=mid or opponent_id=mid) order by created_at desc;
end $$;

create or replace function public.invite_chug_duel(actor_player uuid,target_season uuid,
  invitation_id uuid,opponent_member uuid,selected_drink text,selected_size text)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare s public.seasons%rowtype; cid uuid; at_time timestamptz := statement_timestamp(); night date;
  old public.chug_duels%rowtype;
begin
  select * into s from public.seasons where id=target_season;
  if not found then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  select id into cid from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
  if cid is null then raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into old from public.chug_duels where id=invitation_id;
  if found then
    if old.challenger_id<>cid or old.season_id<>target_season or old.opponent_id<>opponent_member
      or old.drink_type is distinct from selected_drink or old.size is distinct from selected_size then
      raise exception 'permission_denied';
    end if;
    return query select * from public.chug_duels where id=invitation_id; return;
  end if;
  if s.scoring_version<>'v1' or s.scoring_rules is null then raise exception 'scoring_setup_required'; end if;
  if at_time<s.starts_at or at_time>=s.ends_at or not public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules) then
    raise exception 'scoring_closed'; end if;
  perform public._scoring_points(s.scoring_rules,selected_drink,selected_size);
  perform public._check_chug_pair(cid,opponent_member,s.lobby_id);
  night := public._chug_night(at_time,s.timezone_name);
  perform public._check_chug_slots(cid,opponent_member,night,invitation_id);
  if exists(select 1 from public.chug_duels where challenger_id=cid and status='invited') then raise exception 'duel_pending'; end if;
  insert into public.chug_duels(id,season_id,challenger_id,opponent_id,game_night,drink_type,size,created_at,expires_at)
    values(invitation_id,target_season,cid,opponent_member,night,selected_drink,selected_size,at_time,at_time+interval '10 minutes');
  return query select * from public.chug_duels where id=invitation_id;
end $$;

create or replace function public.chug_duel_action(actor_player uuid,target_duel uuid,
  selected_action text,winning_member uuid default null)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare d public.chug_duels%rowtype; s public.seasons%rowtype; mid uuid;
  at_time timestamptz := statement_timestamp(); losing_entry uuid; winner_account uuid;
begin
  select * into d from public.chug_duels where id=target_duel;
  if not found then raise exception 'permission_denied'; end if;
  select * into s from public.seasons where id=d.season_id;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  select id into mid from public.lobby_memberships where player_id=actor_player and lobby_id=s.lobby_id;
  if mid is null or mid not in (d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
  if selected_action in ('accept','decline') and mid<>d.opponent_id then raise exception 'permission_denied'; end if;
  if selected_action in ('cancel','arm','finish') and mid<>d.challenger_id then raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into d from public.chug_duels where id=target_duel for update;
  -- Terminal outcomes are immutable, including retries after a lost response.
  if d.status in ('completed','aborted','declined','cancelled','expired') then
    return query select * from public.chug_duels where id=target_duel; return;
  end if;
  if selected_action='accept' then
    if d.status='invited' then
      perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
      perform public._check_chug_slots(d.challenger_id,d.opponent_id,d.game_night,d.id);
      update public.chug_duels set status='accepted',accepted_at=at_time,expires_at=at_time+interval '10 minutes' where id=d.id;
    end if;
  elsif selected_action='decline' and d.status='invited' then
    update public.chug_duels set status='declined',finished_at=at_time where id=d.id;
  elsif selected_action='cancel' and d.status in ('invited','accepted') then
    update public.chug_duels set status='cancelled',finished_at=at_time where id=d.id;
  elsif selected_action='abort' then
    update public.chug_duels set status=case when d.status='started' then 'aborted' else 'cancelled' end,
      finished_at=at_time where id=d.id;
  elsif selected_action='arm' and d.status='started' then
    update public.chug_duels set play_at=coalesce(play_at,at_time+interval '3 seconds') where id=d.id;
  elsif selected_action='finish' and d.status='started' then
    if winning_member is null or winning_member not in (d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
    if d.play_at is null or at_time<d.play_at then raise exception 'duel_early'; end if;
    losing_entry := case when winning_member=d.challenger_id then d.opponent_entry_id else d.challenger_entry_id end;
    select coalesce(team_id,membership_id) into winner_account from public.drink_entries
      where id=case when winning_member=d.challenger_id then d.challenger_entry_id else d.opponent_entry_id end;
    if winner_account is null then raise exception 'duel_unavailable'; end if;
    update public.drink_entries set duel_transfer_to=winner_account,
      duel_transfer_order=nextval('public.drink_entries_event_order_seq') where id=losing_entry;
    update public.chug_duels set status='completed',winner_id=winning_member,finished_at=at_time where id=d.id;
  else raise exception 'duel_unavailable';
  end if;
  return query select * from public.chug_duels where id=target_duel;
end $$;

create or replace function public.start_chug_duel(actor_player uuid,target_duel uuid,
  verified_territory text,location_result text,photo_received_at timestamptz)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare d public.chug_duels%rowtype; s public.seasons%rowtype; opponent_player uuid;
  at_time timestamptz := statement_timestamp();
begin
  select * into d from public.chug_duels where id=target_duel;
  if not found then raise exception 'permission_denied'; end if;
  select * into s from public.seasons where id=d.season_id;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  if not exists(select 1 from public.lobby_memberships where id=d.challenger_id and player_id=actor_player and lobby_id=s.lobby_id) then
    raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into d from public.chug_duels where id=target_duel for update;
  if d.status in ('started','completed','aborted') then
    return query select * from public.chug_duels where id=target_duel; return;
  end if;
  if d.status<>'accepted' then raise exception 'duel_unavailable'; end if;
  perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
  perform public._check_chug_slots(d.challenger_id,d.opponent_id,d.game_night,d.id);
  if photo_received_at is null or photo_received_at<d.accepted_at or photo_received_at>at_time
    then raise exception 'invalid_photo'; end if;
  -- Python verifies the shared camera bytes and current phone GPS. Only the
  -- server service role can call this RPC, like accept_scoring_checkin.
  select player_id into opponent_player from public.lobby_memberships where id=d.opponent_id;
  perform public.accept_scoring_checkin(actor_player,d.challenger_entry_id,d.challenger_id,s.id,
    d.drink_type,d.size,verified_territory,location_result,s.lobby_id::text||'/'||d.challenger_entry_id::text||'.jpg',photo_received_at);
  perform public.accept_scoring_checkin(opponent_player,d.opponent_entry_id,d.opponent_id,s.id,
    d.drink_type,d.size,verified_territory,location_result,s.lobby_id::text||'/'||d.opponent_entry_id::text||'.jpg',photo_received_at);
  update public.drink_entries set duel_id=d.id where id in (d.challenger_entry_id,d.opponent_entry_id);
  update public.chug_duels set status='started',started_at=at_time,expires_at=at_time+interval '10 minutes' where id=d.id;
  return query select * from public.chug_duels where id=target_duel;
end $$;

create or replace function public._freeze_chug_selection()
returns trigger language plpgsql set search_path=public as $$
begin
  if old.duel_id is not null and row(new.drink_type,new.size,new.amount,new.duel_id)
    is distinct from row(old.drink_type,old.size,old.amount,old.duel_id) then
    raise exception 'duel_entry_locked'; end if;
  return new;
end $$;
drop trigger if exists freeze_chug_selection on public.drink_entries;
create trigger freeze_chug_selection before update on public.drink_entries
  for each row execute function public._freeze_chug_selection();

revoke all on function public._chug_night(timestamptz,text),public._expire_chug_duels(uuid,timestamptz),
  public._check_chug_pair(uuid,uuid,uuid),public._check_chug_slots(uuid,uuid,date,uuid),public._freeze_chug_selection(),
  public.list_chug_duels(uuid,uuid),public.invite_chug_duel(uuid,uuid,uuid,uuid,text,text),
  public.chug_duel_action(uuid,uuid,text,uuid),public.start_chug_duel(uuid,uuid,text,text,timestamptz)
  from public,anon,authenticated;
grant execute on function public._chug_night(timestamptz,text),public._expire_chug_duels(uuid,timestamptz),
  public._check_chug_pair(uuid,uuid,uuid),public._check_chug_slots(uuid,uuid,date,uuid),
  public.list_chug_duels(uuid,uuid),public.invite_chug_duel(uuid,uuid,uuid,uuid,text,text),
  public.chug_duel_action(uuid,uuid,text,uuid),public.start_chug_duel(uuid,uuid,text,text,timestamptz) to service_role;
notify pgrst,'reload schema';
commit;
